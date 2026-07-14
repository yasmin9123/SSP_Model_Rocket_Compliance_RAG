from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = PROJECT_ROOT / "governed_data" / "rules.jsonl"
DEFAULT_INPUT_PATH = PROJECT_ROOT / "tests" / "sample_rocket.json"
OUTPUT_PATH = PROJECT_ROOT / "tests" / "sample_compliance_result.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {path}: {error}"
                ) from error

    return records


def is_missing(value: Any) -> bool:
    return value is None or value == ""


def classify_rocket(data: dict[str, Any]) -> tuple[str | None, list[str]]:
    """
    Determine the FAA rocket class using the supplied rocket information.

    Returns:
        A tuple containing:
        - The determined class, or None when information is insufficient
        - A list of explanation messages
    """

    explanations: list[str] = []

    required_class_1_fields = [
        "propellant_mass_grams",
        "propellant_burn_type",
        "rocket_materials",
        "contains_substantial_metal_parts",
        "total_liftoff_mass_grams",
    ]

    missing_fields = [
        field
        for field in required_class_1_fields
        if is_missing(data.get(field))
    ]

    if missing_fields:
        explanations.append(
            "Unable to fully test Class 1 status because these fields are "
            f"missing: {', '.join(missing_fields)}."
        )
    else:
        allowed_materials = {
            "paper",
            "wood",
            "breakable plastic",
            "cardboard",
        }

        reported_materials = {
            str(material).strip().lower()
            for material in data["rocket_materials"]
        }

        class_1_conditions = {
            "propellant_mass": data["propellant_mass_grams"] <= 125,
            "slow_burning": data["propellant_burn_type"] == "slow-burning",
            "materials": reported_materials.issubset(allowed_materials),
            "no_substantial_metal": (
                data["contains_substantial_metal_parts"] is False
            ),
            "total_mass": data["total_liftoff_mass_grams"] <= 1500,
        }

        if all(class_1_conditions.values()):
            explanations.append(
                "The supplied information satisfies all listed FAA Class 1 "
                "classification conditions."
            )
            return "Class 1", explanations

        failed_conditions = [
            name
            for name, passed in class_1_conditions.items()
            if not passed
        ]

        explanations.append(
            "The rocket does not satisfy all Class 1 conditions. Failed "
            f"conditions: {', '.join(failed_conditions)}."
        )

    total_impulse = data.get("combined_total_impulse_newton_seconds")

    if is_missing(total_impulse):
        explanations.append(
            "Combined total impulse is missing, so Class 2 versus Class 3 "
            "cannot be determined."
        )
        return None, explanations

    if total_impulse <= 40960:
        explanations.append(
            "The rocket does not qualify as Class 1 and its reported combined "
            "total impulse is no more than 40,960 N·s."
        )
        return "Class 2", explanations

    explanations.append(
        "The rocket does not qualify as Class 1 and its reported combined "
        "total impulse exceeds 40,960 N·s."
    )
    return "Class 3", explanations


def rule_applies(rule: dict[str, Any], rocket_class: str | None) -> bool:
    applies_to = rule.get("applies_to")

    if applies_to is None:
        return True

    if applies_to == "All amateur rockets":
        return True

    if applies_to == "Class 1 candidate":
        return True

    if applies_to == "All rockets other than Class 1":
        return rocket_class in {"Class 2", "Class 3"}

    if isinstance(applies_to, list):
        return rocket_class in applies_to

    return applies_to == rocket_class


def condition_is_active(
    rule: dict[str, Any],
    data: dict[str, Any],
) -> tuple[bool, str | None]:
    condition_field = rule.get("condition_field")

    if not condition_field:
        return True, None

    actual_value = data.get(condition_field)

    if is_missing(actual_value):
        return False, (
            f"Condition field '{condition_field}' is missing, so this rule "
            "cannot yet be applied."
        )

    expected_value = rule.get("condition_value")

    if actual_value != expected_value:
        return False, None

    return True, None


def make_result(
    rule: dict[str, Any],
    status: str,
    message: str,
    actual_value: Any = None,
    required_value: Any = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "status": status,
        "citation": rule.get("citation"),
        "authority": rule.get("authority"),
        "category": rule.get("category"),
        "actual_value": actual_value,
        "required_value": required_value,
        "message": message,
    }


def evaluate_rule(
    rule: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    operator = rule.get("operator")

    if "input_fields" in rule:
        input_fields = rule["input_fields"]
        values = {field: data.get(field) for field in input_fields}

        missing_fields = [
            field
            for field, value in values.items()
            if is_missing(value)
        ]

        if missing_fields:
            return make_result(
                rule,
                "INSUFFICIENT_INFORMATION",
                rule.get(
                    "missing_message",
                    f"Missing fields: {', '.join(missing_fields)}",
                ),
                actual_value=values,
            )
    else:
        input_field = rule.get("input_field")
        value = data.get(input_field)

        if is_missing(value):
            return make_result(
                rule,
                "INSUFFICIENT_INFORMATION",
                rule.get(
                    "missing_message",
                    f"Missing field: {input_field}",
                ),
            )

    if operator == "less_than_or_equal":
        value = data[rule["input_field"]]
        threshold = rule["threshold"]
        passed = value <= threshold

        return make_result(
            rule,
            "PASS" if passed else "FAIL",
            rule["pass_message"] if passed else rule["fail_message"],
            actual_value=value,
            required_value=f"≤ {threshold} {rule.get('unit', '')}".strip(),
        )

    if operator == "greater_than_or_equal":
        value = data[rule["input_field"]]
        threshold = rule["threshold"]
        passed = value >= threshold

        return make_result(
            rule,
            "PASS" if passed else "FAIL",
            rule["pass_message"] if passed else rule["fail_message"],
            actual_value=value,
            required_value=f"≥ {threshold} {rule.get('unit', '')}".strip(),
        )

    if operator == "equals":
        value = data[rule["input_field"]]
        expected_value = rule["expected_value"]
        passed = value == expected_value

        return make_result(
            rule,
            "PASS" if passed else "FAIL",
            rule["pass_message"] if passed else rule["fail_message"],
            actual_value=value,
            required_value=expected_value,
        )

    if operator == "all_values_allowed":
        values = {
            str(value).strip().lower()
            for value in data[rule["input_field"]]
        }
        allowed_values = {
            str(value).strip().lower()
            for value in rule["allowed_values"]
        }

        passed = values.issubset(allowed_values)

        status = "PASS" if passed else "HUMAN_REVIEW_REQUIRED"

        return make_result(
            rule,
            status,
            rule["pass_message"] if passed else rule["fail_message"],
            actual_value=sorted(values),
            required_value=sorted(allowed_values),
        )

    if operator == "greater_than_or_equal_unless_authorized":
        distance = data[rule["input_field"]]
        authorization = data.get(rule["authorization_field"])
        threshold = rule["threshold"]

        if distance >= threshold or authorization is True:
            return make_result(
                rule,
                "PASS",
                rule["pass_message"],
                actual_value={
                    "distance": distance,
                    "authorization": authorization,
                },
                required_value=(
                    f"At least {threshold} {rule.get('unit', '')}, "
                    "unless authorized"
                ),
            )

        if authorization is None:
            return make_result(
                rule,
                "INSUFFICIENT_INFORMATION",
                rule["missing_message"],
                actual_value={
                    "distance": distance,
                    "authorization": authorization,
                },
            )

        return make_result(
            rule,
            "FAIL",
            rule["fail_message"],
            actual_value={
                "distance": distance,
                "authorization": authorization,
            },
        )

    if operator == "greater_than_or_equal_dynamic":
        altitude = data["planned_altitude_agl_feet"]
        separation = data["nearest_unassociated_person_or_property_feet"]
        required_separation = max(1500, altitude / 4)
        passed = separation >= required_separation

        return make_result(
            rule,
            "PASS" if passed else "FAIL",
            rule["pass_message"] if passed else rule["fail_message"],
            actual_value=separation,
            required_value=f"≥ {required_separation} feet",
        )

    if operator == "adult_present_and_age_at_least":
        adult_present = data["responsible_adult_present"]
        adult_age = data["responsible_adult_age"]
        threshold = rule["threshold"]

        passed = adult_present is True and adult_age >= threshold

        return make_result(
            rule,
            "PASS" if passed else "FAIL",
            rule["pass_message"] if passed else rule["fail_message"],
            actual_value={
                "adult_present": adult_present,
                "adult_age": adult_age,
            },
            required_value=f"Adult present and age ≥ {threshold}",
        )

    if operator == "notification_between_hours":
        notification_completed = data["atc_notification_completed"]
        notification_hours = data["notification_hours_before_launch"]
        minimum_hours = rule["minimum_hours"]
        maximum_hours = rule["maximum_hours"]

        passed = (
            notification_completed is True
            and minimum_hours <= notification_hours <= maximum_hours
        )

        return make_result(
            rule,
            "PASS" if passed else "FAIL",
            rule["pass_message"] if passed else rule["fail_message"],
            actual_value={
                "notification_completed": notification_completed,
                "hours_before_launch": notification_hours,
            },
            required_value=(
                f"Notification completed between {minimum_hours} and "
                f"{maximum_hours} hours before launch"
            ),
        )

    return make_result(
        rule,
        "HUMAN_REVIEW_REQUIRED",
        f"Unsupported rule operator: {operator}",
    )


def determine_overall_status(results: list[dict[str, Any]]) -> str:
    statuses = {result["status"] for result in results}

    if "FAIL" in statuses:
        return "FAIL"

    if "HUMAN_REVIEW_REQUIRED" in statuses:
        return "HUMAN_REVIEW_REQUIRED"

    if "INSUFFICIENT_INFORMATION" in statuses:
        return "INSUFFICIENT_INFORMATION"

    if statuses == {"NOT_APPLICABLE"}:
        return "NOT_APPLICABLE"

    return "PASS"


def run_compliance_check(
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]:
    data = load_json(input_path)
    rules = load_jsonl(RULES_PATH)

    rocket_class, classification_notes = classify_rocket(data)

    declared_class = data.get("rocket_class")

    if declared_class not in {None, "Unknown", rocket_class}:
        classification_notes.append(
            f"The declared class '{declared_class}' conflicts with the "
            f"calculated class '{rocket_class}'. Human review is required."
        )

    results: list[dict[str, Any]] = []

    for rule in rules:
        if not rule_applies(rule, rocket_class):
            results.append(
                make_result(
                    rule,
                    "NOT_APPLICABLE",
                    f"This rule does not apply to {rocket_class or 'an undetermined class'}.",
                )
            )
            continue

        active, condition_message = condition_is_active(rule, data)

        if not active:
            if condition_message:
                results.append(
                    make_result(
                        rule,
                        "INSUFFICIENT_INFORMATION",
                        condition_message,
                    )
                )
            else:
                results.append(
                    make_result(
                        rule,
                        "NOT_APPLICABLE",
                        "The condition that activates this rule was not met.",
                    )
                )
            continue

        results.append(evaluate_rule(rule, data))

    overall_status = determine_overall_status(results)

    if declared_class not in {None, "Unknown", rocket_class}:
        overall_status = "HUMAN_REVIEW_REQUIRED"

    return {
        "rocket_name": data.get("rocket_name"),
        "calculated_rocket_class": rocket_class,
        "declared_rocket_class": declared_class,
        "classification_notes": classification_notes,
        "overall_status": overall_status,
        "checks": results,
        "disclaimer": (
            "This is a preliminary automated review based only on the supplied "
            "information and included FAA rules. It is not FAA authorization "
            "and does not replace qualified human review."
        ),
    }


def main() -> None:
    try:
        report = run_compliance_check()
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        with OUTPUT_PATH.open("w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, ensure_ascii=False)

        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nResult saved to: {OUTPUT_PATH}")

    except FileNotFoundError as error:
        raise SystemExit(f"Required file not found: {error.filename}") from error
    except (ValueError, TypeError, KeyError) as error:
        raise SystemExit(f"Compliance check failed: {error}") from error


if __name__ == "__main__":
    main()
