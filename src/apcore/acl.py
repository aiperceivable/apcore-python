"""ACL (Access Control List) types and implementation for apcore.

This module defines the ACLRule dataclass and the ACL class that enforces
pattern-based access control between modules.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import yaml

from apcore.context import Context
from apcore.errors import ACLRuleError, ConfigNotFoundError
from apcore.utils.pattern import match_pattern

__all__ = ["ACLRule", "AuditEntry", "ACL"]


@dataclass
class ACLRule:
    """A single access control rule.

    Rules are evaluated in order by the ACL system. Each rule specifies
    caller patterns, target patterns, and an effect (allow/deny).
    """

    callers: list[str]
    targets: list[str]
    effect: str
    description: str = ""
    conditions: dict[str, Any] | None = None


@dataclass(frozen=True)
class AuditEntry:
    """Structured record of an ACL check decision."""

    timestamp: str  # ISO 8601
    caller_id: str
    target_id: str
    decision: str  # "allow" or "deny"
    reason: str  # "rule_match", "default_effect", "no_rules"
    matched_rule: str | None = None  # Rule description (immutable snapshot)
    matched_rule_index: int | None = None
    identity_type: str | None = None
    roles: tuple[str, ...] = field(default_factory=tuple)
    call_depth: int | None = None
    trace_id: str | None = None


class ACL:
    """Access Control List with pattern-based rules and first-match-wins evaluation.

    Implements PROTOCOL_SPEC section 6 for module access control.

    Thread safety:
        Internally synchronized. All public methods (check, add_rule,
        remove_rule, reload) are safe to call concurrently.
    """

    def __init__(
        self,
        rules: list[ACLRule],
        default_effect: str = "deny",
        *,
        audit_logger: Callable[[AuditEntry], None] | None = None,
    ) -> None:
        """Initialize ACL with ordered rules and a default effect.

        Args:
            rules: Ordered list of ACL rules (first match wins).
            default_effect: Effect when no rule matches ('allow' or 'deny').
            audit_logger: Optional callback invoked with an AuditEntry for
                every check() call. Useful for structured audit trails.
        """
        self._rules: list[ACLRule] = list(rules)
        self._default_effect: str = default_effect
        self._yaml_path: str | None = None
        self._audit_logger: Callable[[AuditEntry], None] | None = audit_logger
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self.debug: bool = False

    @classmethod
    def load(cls, yaml_path: str) -> ACL:
        """Load ACL configuration from a YAML file.

        Args:
            yaml_path: Path to the YAML configuration file.

        Returns:
            A new ACL instance configured from the YAML file.

        Raises:
            ConfigNotFoundError: If the file does not exist.
            ACLRuleError: If the YAML is invalid or has structural errors.
        """
        if not os.path.isfile(yaml_path):
            raise ConfigNotFoundError(config_path=yaml_path)

        with open(yaml_path, encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ACLRuleError(f"Invalid YAML in {yaml_path}: {e}") from e

        if not isinstance(data, dict):
            raise ACLRuleError(f"ACL config must be a mapping, got {type(data).__name__}")

        if "rules" not in data:
            raise ACLRuleError("ACL config missing required 'rules' key")

        raw_rules = data["rules"]
        if not isinstance(raw_rules, list):
            raise ACLRuleError(f"'rules' must be a list, got {type(raw_rules).__name__}")

        default_effect: str = data.get("default_effect", "deny")
        rules: list[ACLRule] = []

        for i, raw_rule in enumerate(raw_rules):
            if not isinstance(raw_rule, dict):
                raise ACLRuleError(f"Rule {i} must be a mapping, got {type(raw_rule).__name__}")

            for key in ("callers", "targets", "effect"):
                if key not in raw_rule:
                    raise ACLRuleError(f"Rule {i} missing required key '{key}'")

            effect = raw_rule["effect"]
            if effect not in ("allow", "deny"):
                raise ACLRuleError(f"Rule {i} has invalid effect '{effect}', must be 'allow' or 'deny'")

            callers = raw_rule["callers"]
            if not isinstance(callers, list):
                raise ACLRuleError(f"Rule {i} 'callers' must be a list, got {type(callers).__name__}")

            targets = raw_rule["targets"]
            if not isinstance(targets, list):
                raise ACLRuleError(f"Rule {i} 'targets' must be a list, got {type(targets).__name__}")

            rules.append(
                ACLRule(
                    callers=callers,
                    targets=targets,
                    effect=effect,
                    description=raw_rule.get("description", ""),
                    conditions=raw_rule.get("conditions"),
                )
            )

        acl = cls(rules=rules, default_effect=default_effect)
        acl._yaml_path = yaml_path
        return acl

    def check(
        self,
        caller_id: str | None,
        target_id: str,
        context: Context | None = None,
    ) -> bool:
        """Check if a call from caller_id to target_id is allowed.

        Args:
            caller_id: The calling module ID, or None for external calls.
            target_id: The target module ID being called.
            context: Optional execution context for conditional rules.

        Returns:
            True if the call is allowed, False if denied.
        """
        effective_caller = "@external" if caller_id is None else caller_id

        with self._lock:
            rules = list(self._rules)
            default_effect = self._default_effect
            audit_logger = self._audit_logger

        for idx, rule in enumerate(rules):
            if self._matches_rule(rule, effective_caller, target_id, context):
                decision = rule.effect == "allow"
                self._logger.debug(
                    "ACL check: caller=%s target=%s decision=%s rule=%s",
                    caller_id,
                    target_id,
                    "allow" if decision else "deny",
                    rule.description or "(no description)",
                )
                if audit_logger is not None:
                    entry = self._build_audit_entry(
                        caller_id=effective_caller,
                        target_id=target_id,
                        decision="allow" if decision else "deny",
                        reason="rule_match",
                        matched_rule=rule,
                        matched_rule_index=idx,
                        context=context,
                    )
                    audit_logger(entry)
                return decision

        default_decision = default_effect == "allow"
        self._logger.debug(
            "ACL check: caller=%s target=%s decision=%s rule=default",
            caller_id,
            target_id,
            "allow" if default_decision else "deny",
        )
        if audit_logger is not None:
            reason = "no_rules" if not rules else "default_effect"
            entry = self._build_audit_entry(
                caller_id=effective_caller,
                target_id=target_id,
                decision="allow" if default_decision else "deny",
                reason=reason,
                matched_rule=None,
                matched_rule_index=None,
                context=context,
            )
            audit_logger(entry)
        return default_decision

    def _build_audit_entry(
        self,
        *,
        caller_id: str,
        target_id: str,
        decision: str,
        reason: str,
        matched_rule: ACLRule | None,
        matched_rule_index: int | None,
        context: Context | None,
    ) -> AuditEntry:
        """Build an AuditEntry, extracting optional fields from context."""
        identity_type: str | None = None
        roles: tuple[str, ...] = ()
        call_depth: int | None = None
        trace_id: str | None = None

        if context is not None:
            trace_id = context.trace_id
            call_depth = len(context.call_chain)
            if context.identity is not None:
                identity_type = context.identity.type
                roles = tuple(context.identity.roles)

        return AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            caller_id=caller_id,
            target_id=target_id,
            decision=decision,
            reason=reason,
            matched_rule=matched_rule.description if matched_rule is not None else None,
            matched_rule_index=matched_rule_index,
            identity_type=identity_type,
            roles=roles,
            call_depth=call_depth,
            trace_id=trace_id,
        )

    def _match_pattern(self, pattern: str, value: str, context: Context | None = None) -> bool:
        """Match a single pattern against a value, with special pattern handling.

        Handles @external and @system patterns locally, delegates all
        other patterns to the foundation match_pattern() utility.
        """
        if pattern == "@external":
            return value == "@external"
        if pattern == "@system":
            return context is not None and context.identity is not None and context.identity.type == "system"
        return match_pattern(pattern, value)

    def _matches_rule(
        self,
        rule: ACLRule,
        caller: str,
        target: str,
        context: Context | None,
    ) -> bool:
        """Check if a single rule matches the caller and target.

        All of the following must be true for a match:
        1. At least one caller pattern matches the caller (OR logic).
        2. At least one target pattern matches the target (OR logic).
        3. If conditions are present, they must all be satisfied.
        """
        caller_match = any(self._match_pattern(p, caller, context) for p in rule.callers)
        if not caller_match:
            return False

        target_match = any(self._match_pattern(p, target, context) for p in rule.targets)
        if not target_match:
            return False

        if rule.conditions is not None:
            if not self._check_conditions(rule.conditions, context):
                return False

        return True

    def _check_conditions(self, conditions: dict[str, Any], context: Context | None) -> bool:
        """Evaluate conditional rule parameters against the execution context.

        Returns False if any condition is not satisfied.
        """
        if context is None:
            return False

        if "identity_types" in conditions:
            if context.identity is None or context.identity.type not in conditions["identity_types"]:
                return False

        if "roles" in conditions:
            if context.identity is None:
                return False
            if not set(context.identity.roles) & set(conditions["roles"]):
                return False

        if "max_call_depth" in conditions:
            if len(context.call_chain) > conditions["max_call_depth"]:
                return False

        return True

    def add_rule(self, rule: ACLRule) -> None:
        """Add a rule at position 0 (highest priority).

        Args:
            rule: The ACLRule to add.
        """
        with self._lock:
            self._rules.insert(0, rule)

    def remove_rule(self, callers: list[str], targets: list[str]) -> bool:
        """Remove the first rule matching the given callers and targets.

        Args:
            callers: The caller patterns to match.
            targets: The target patterns to match.

        Returns:
            True if a rule was found and removed, False otherwise.
        """
        with self._lock:
            for i, rule in enumerate(self._rules):
                if rule.callers == callers and rule.targets == targets:
                    self._rules.pop(i)
                    return True
            return False

    def reload(self) -> None:
        """Re-read the ACL from the original YAML file.

        Only works if the ACL was created via ACL.load().
        Raises ACLRuleError if no YAML path was stored.
        """
        with self._lock:
            yaml_path = self._yaml_path
        if yaml_path is None:
            raise ACLRuleError("Cannot reload: ACL was not loaded from a YAML file")
        reloaded = ACL.load(yaml_path)
        with self._lock:
            self._rules = reloaded._rules
            self._default_effect = reloaded._default_effect
