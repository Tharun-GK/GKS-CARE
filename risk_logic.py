from dataclasses import asdict, dataclass
import math
from collections.abc import Mapping


@dataclass(frozen=True)
class RiskThresholds:
    spo2_high_below: float = 92
    spo2_medium_below: float = 95
    heart_rate_high_above: float = 110
    heart_rate_medium_above: float = 95
    temperature_note_above_f: float = 100
    score_heart_rate_high_above: float = 120
    score_heart_rate_medium_above: float = 100
    score_spo2_low_below: float = 90
    score_spo2_medium_below: float = 95
    score_temperature_high_above_f: float = 101
    score_temperature_medium_above_f: float = 99.5

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Risk threshold '{name}' must be a finite number.")
            if not math.isfinite(value):
                raise ValueError(f"Risk threshold '{name}' must be a finite number.")

        if self.spo2_high_below >= self.spo2_medium_below:
            raise ValueError("The demo SpO2 high threshold must be below its medium threshold.")
        if self.heart_rate_medium_above >= self.heart_rate_high_above:
            raise ValueError(
                "The demo heart-rate medium threshold must be below its high threshold."
            )
        if not 0 <= self.spo2_high_below <= 100 or not 0 <= self.spo2_medium_below <= 100:
            raise ValueError("Demo SpO2 thresholds must be between 0 and 100 percent.")
        if self.heart_rate_high_above <= 0 or self.heart_rate_medium_above <= 0:
            raise ValueError("Demo heart-rate thresholds must be greater than zero.")
        if self.score_heart_rate_medium_above >= self.score_heart_rate_high_above:
            raise ValueError(
                "The demo score heart-rate medium threshold must be below its high threshold."
            )
        if self.score_heart_rate_medium_above <= 0 or self.score_heart_rate_high_above <= 0:
            raise ValueError("Demo score heart-rate thresholds must be greater than zero.")
        if self.score_spo2_low_below >= self.score_spo2_medium_below:
            raise ValueError("The demo score SpO2 low threshold must be below its medium threshold.")
        if (
            not 0 <= self.score_spo2_low_below <= 100
            or not 0 <= self.score_spo2_medium_below <= 100
        ):
            raise ValueError("Demo score SpO2 thresholds must be between 0 and 100 percent.")
        if self.score_temperature_medium_above_f >= self.score_temperature_high_above_f:
            raise ValueError(
                "The demo score temperature medium threshold must be below its high threshold."
            )

    @classmethod
    def from_mapping(cls, values):
        if values is None:
            return cls()
        if isinstance(values, cls):
            return values
        if not isinstance(values, Mapping):
            raise ValueError("Risk thresholds must be provided as a mapping.")

        known_fields = set(cls.__dataclass_fields__)
        unknown_fields = set(values) - known_fields
        if unknown_fields:
            raise ValueError(
                "Unknown risk threshold configuration: "
                + ", ".join(sorted(map(str, unknown_fields)))
            )
        merged = asdict(cls())
        merged.update(values)
        return cls(**merged)


REQUIRED_VITALS = ("hr", "spo2", "temp")
RISK_SEVERITY = {"Low": "low", "Medium": "moderate", "High": "high"}
RISK_STATUS = {
    "Low": "No Demo Threshold Flagged",
    "Medium": "Demo Review Suggested",
    "High": "Demo High Pattern — Review",
}
NEXT_STEPS = {
    "Low": (
        "No configured demonstration threshold was triggered. This does not rule out "
        "illness; review the measurements in context."
    ),
    "Medium": (
        "A demonstration rule was triggered. Review the measurements and data quality "
        "with a qualified clinician."
    ),
    "High": (
        "A higher-severity demonstration rule was triggered. Promptly review the "
        "measurements with a qualified clinician; this is not a diagnosis."
    ),
    "Unavailable": (
        "A risk level could not be determined. Check the missing or invalid "
        "measurements before interpreting this demonstration."
    ),
}


@dataclass(frozen=True)
class RiskAssessment:
    risk: str
    severity: str
    status: str
    factors: tuple
    next_step: str
    data_quality: str

    @property
    def reasons(self):
        return [factor["label"] for factor in self.factors]

    def to_dict(self):
        return {
            "risk": self.risk,
            "severity": self.severity,
            "status": self.status,
            "method": "deterministic_demo_rules",
            "reasons": self.reasons,
            "factors": list(self.factors),
            "next_step": self.next_step,
            "data_quality": {"status": self.data_quality},
            "threshold_source": "inherited_demo_configuration_not_clinical_guidance",
            "clinically_validated": False,
        }


def _read_number(row, name):
    try:
        value = row[name]
    except (KeyError, TypeError, IndexError):
        return None

    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None
    return number


def _unavailable_assessment(issues):
    factors = tuple(
        {
            "code": "data_quality",
            "label": issue,
            "observed_value": None,
            "threshold": None,
            "unit": None,
            "affects_risk": True,
        }
        for issue in issues
    )
    return RiskAssessment(
        risk="Unavailable",
        severity="unknown",
        status="Assessment Unavailable",
        factors=factors,
        next_step=NEXT_STEPS["Unavailable"],
        data_quality="incomplete_or_invalid",
    )


def assess_vitals(row, previous_row=None, thresholds=None):
    configured_thresholds = RiskThresholds.from_mapping(thresholds)
    values = {name: _read_number(row, name) for name in REQUIRED_VITALS}
    issues = [
        f"{name} is missing or is not a finite number."
        for name, value in values.items()
        if value is None
    ]

    if values["hr"] is not None and values["hr"] <= 0:
        issues.append("Heart rate must be greater than zero.")
    if values["spo2"] is not None and not 0 <= values["spo2"] <= 100:
        issues.append("SpO2 must be between 0 and 100 percent.")

    if issues:
        return _unavailable_assessment(issues)

    heart_rate = values["hr"]
    spo2 = values["spo2"]
    temperature = values["temp"]
    factors = []
    severity_rank = 0

    if spo2 < configured_thresholds.spo2_high_below:
        severity_rank = max(severity_rank, 2)
        factors.append({
            "code": "spo2_demo_high",
            "label": "SpO2 is below the configured demonstration high threshold.",
            "observed_value": spo2,
            "threshold": configured_thresholds.spo2_high_below,
            "unit": "%",
            "affects_risk": True,
        })
    elif spo2 < configured_thresholds.spo2_medium_below:
        severity_rank = max(severity_rank, 1)
        factors.append({
            "code": "spo2_demo_medium",
            "label": "SpO2 is below the configured demonstration medium threshold.",
            "observed_value": spo2,
            "threshold": configured_thresholds.spo2_medium_below,
            "unit": "%",
            "affects_risk": True,
        })

    if heart_rate > configured_thresholds.heart_rate_high_above:
        severity_rank = max(severity_rank, 2)
        factors.append({
            "code": "heart_rate_demo_high",
            "label": "Heart rate is above the configured demonstration high threshold.",
            "observed_value": heart_rate,
            "threshold": configured_thresholds.heart_rate_high_above,
            "unit": "bpm",
            "affects_risk": True,
        })
    elif heart_rate > configured_thresholds.heart_rate_medium_above:
        severity_rank = max(severity_rank, 1)
        factors.append({
            "code": "heart_rate_demo_medium",
            "label": "Heart rate is above the configured demonstration medium threshold.",
            "observed_value": heart_rate,
            "threshold": configured_thresholds.heart_rate_medium_above,
            "unit": "bpm",
            "affects_risk": True,
        })

    if temperature > configured_thresholds.temperature_note_above_f:
        factors.append({
            "code": "temperature_demo_note",
            "label": "Temperature exceeds a demonstration note threshold.",
            "observed_value": temperature,
            "threshold": configured_thresholds.temperature_note_above_f,
            "unit": "°F",
            "affects_risk": False,
        })

    if previous_row is not None:
        previous_heart_rate = _read_number(previous_row, "hr")
        previous_spo2 = _read_number(previous_row, "spo2")
        if previous_spo2 is not None and spo2 < previous_spo2:
            factors.append({
                "code": "spo2_demo_trend",
                "label": "SpO2 is lower than the previous sample.",
                "observed_value": spo2,
                "threshold": previous_spo2,
                "unit": "%",
                "affects_risk": False,
            })
        if previous_heart_rate is not None and heart_rate > previous_heart_rate:
            factors.append({
                "code": "heart_rate_demo_trend",
                "label": "Heart rate is higher than the previous sample.",
                "observed_value": heart_rate,
                "threshold": previous_heart_rate,
                "unit": "bpm",
                "affects_risk": False,
            })

    risk = ("Low", "Medium", "High")[severity_rank]
    return RiskAssessment(
        risk=risk,
        severity=RISK_SEVERITY[risk],
        status=RISK_STATUS[risk],
        factors=tuple(factors),
        next_step=NEXT_STEPS[risk],
        data_quality="complete",
    )


def calculate_risk(row, prev_row=None):
    assessment = assess_vitals(row, prev_row)
    return assessment.risk, assessment.reasons
