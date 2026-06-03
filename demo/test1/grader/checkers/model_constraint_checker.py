"""Model constraint checker v3."""

from __future__ import annotations

from typing import Any

from ..models import CheckReport, SubmissionData


class ModelConstraintChecker:
    """Check the clear, directly auto-verifiable model constraints."""

    checker_name = "Model Constraint Checker"
    HORIZON = 72
    TOLERANCE = 1e-6
    SAMPLE_LIMIT = 10

    def check(self, submission_data: SubmissionData) -> CheckReport:
        report = CheckReport(checker_name=self.checker_name)
        processor_settings = submission_data.processor_settings or {}
        schedule_result = submission_data.schedule_result

        generators = self._generators(processor_settings)
        renewable_capacity = self._renewable_capacity(processor_settings)
        renewable_forecast = self._renewable_forecast(processor_settings)
        storages = self._storages(processor_settings)
        charging_job_targets = self._charging_job_targets(processor_settings)
        charging_jobs = set(charging_job_targets)

        self._check_schedule_device_fields(
            set(generators) | set(renewable_capacity) | set(storages),
            set(storages),
            schedule_result,
            report,
        )
        self._check_generator_output_bounds(generators, schedule_result, report)
        self._check_generator_ramp_limits(generators, schedule_result, report)
        self._check_generator_min_output_ramp_feasibility(generators, report)
        self._check_generator_min_up_time(generators, schedule_result, report)
        self._check_generator_min_down_time(generators, schedule_result, report)
        self._check_generator_initial_on_time(generators, schedule_result, report)
        self._check_generator_initial_off_time(generators, schedule_result, report)
        self._check_renewable_output_upper_bound(renewable_capacity, renewable_forecast, schedule_result, report)
        self._check_storage_discharge_limit(storages, schedule_result, report)
        self._check_storage_charge_limit(storages, charging_job_targets, schedule_result, report)
        self._check_storage_soc_transition(storages, charging_job_targets, schedule_result, report)
        self._check_storage_soc_bounds(storages, schedule_result, report)
        self._check_storage_discharge_available_energy(storages, schedule_result, report)
        self._check_storage_no_simultaneous_charge_discharge(storages, charging_job_targets, schedule_result, report)
        self._check_charging_source_validity(
            set(generators),
            set(renewable_capacity),
            charging_job_targets,
            schedule_result,
            report,
        )
        self._check_device_supply_capacity(storages, charging_job_targets, schedule_result, report)
        self._check_sell_non_negative(schedule_result, report)
        self._check_hourly_energy_balance(charging_jobs, schedule_result, report)
        return report

    def _generators(self, processor_settings: dict[str, Any]) -> dict[str, dict[str, float]]:
        generators: dict[str, dict[str, float]] = {}
        for raw in processor_settings.get("generator", []):
            if not isinstance(raw, dict) or not isinstance(raw.get("generator_id"), str):
                continue
            generator_id = raw["generator_id"]
            missing_fields = [
                field_name
                for field_name in (
                    "output_min",
                    "output_max",
                    "ramp_up_rate",
                    "ramp_down_rate",
                    "initial_energy",
                    "min_up_time",
                    "min_down_time",
                    "initial_on_time",
                    "initial_off_time",
                )
                if field_name not in raw
            ]
            generators[generator_id] = {
                "_missing_fields": missing_fields,
                "output_min": self._to_float(raw.get("output_min"), 0.0),
                "output_max": self._to_float(raw.get("output_max"), 0.0),
                "ramp_up_rate": self._to_float(raw.get("ramp_up_rate"), 0.0),
                "ramp_down_rate": self._to_float(raw.get("ramp_down_rate"), 0.0),
                "initial_energy": self._to_float(raw.get("initial_energy"), 0.0),
                "min_up_time": self._to_float(raw.get("min_up_time"), 0.0),
                "min_down_time": self._to_float(raw.get("min_down_time"), 0.0),
                "initial_on_time": self._to_float(raw.get("initial_on_time"), 0.0),
                "initial_off_time": self._to_float(raw.get("initial_off_time"), 0.0),
            }
        return generators

    def _renewable_capacity(self, processor_settings: dict[str, Any]) -> dict[str, float]:
        capacities: dict[str, float] = {}
        for raw in processor_settings.get("renewable_capacity", []):
            if not isinstance(raw, dict) or not isinstance(raw.get("renewable_id"), str):
                continue
            capacities[raw["renewable_id"]] = self._to_float(raw.get("capacity"), 0.0)
        return capacities

    def _renewable_forecast(self, processor_settings: dict[str, Any]) -> dict[tuple[str, int], float]:
        forecasts: dict[tuple[str, int], float] = {}
        for forecast_group in processor_settings.get("renewable_forecast", []):
            if not isinstance(forecast_group, dict):
                continue
            for renewable_id, entries in forecast_group.items():
                if not isinstance(renewable_id, str) or not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    hour = self._to_int(entry.get("hour"))
                    if hour is None:
                        continue
                    forecasts[(renewable_id, hour)] = self._to_float(entry.get("pv_forecast"), 0.0)
        return forecasts

    def _charging_jobs(self, processor_settings: dict[str, Any]) -> set[str]:
        charging_jobs: set[str] = set()
        for raw in processor_settings.get("charging_jobs", []):
            if isinstance(raw, dict) and isinstance(raw.get("job_id"), str):
                charging_jobs.add(raw["job_id"])
            elif isinstance(raw, str):
                charging_jobs.add(raw)
        return charging_jobs

    def _storages(self, processor_settings: dict[str, Any]) -> dict[str, dict[str, float]]:
        storages: dict[str, dict[str, float]] = {}
        for raw in processor_settings.get("storage", []):
            if not isinstance(raw, dict) or not isinstance(raw.get("storage_id"), str):
                continue
            storage_id = raw["storage_id"]
            storages[storage_id] = {
                "soc_min": self._to_float(raw.get("soc_min"), 0.0),
                "soc_max": self._to_float(raw.get("soc_max"), 0.0),
                "discharge_max": self._to_float(raw.get("discharge_max"), 0.0),
                "charge_max": self._to_float(raw.get("charge_max"), 0.0),
                "soc_init": self._to_float(raw.get("soc_init"), 0.0),
            }
        return storages

    def _charging_job_targets(self, processor_settings: dict[str, Any]) -> dict[str, str]:
        targets: dict[str, str] = {}
        for raw in processor_settings.get("charging_jobs", []):
            if isinstance(raw, dict) and isinstance(raw.get("job_id"), str):
                job_id = raw["job_id"]
                target_storage = raw.get("target_storage")
                if isinstance(target_storage, str):
                    targets[job_id] = target_storage
                elif job_id.endswith("_chg"):
                    targets[job_id] = job_id.removesuffix("_chg")
            elif isinstance(raw, str) and raw.endswith("_chg"):
                targets[raw] = raw.removesuffix("_chg")
        return targets

    def _check_generator_output_bounds(
        self,
        generators: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        violations: list[dict[str, Any]] = []
        missing_specs = self._missing_generator_fields(generators, ("output_min", "output_max"))
        if missing_specs:
            report.add(
                "FAIL",
                "generator_output_bounds",
                "cannot check generator output bounds because processor_settings.generator is missing required fields",
                {"missing_fields": missing_specs},
            )
            return
        for entry in self._schedule_entries(schedule_result):
            t = entry["t"]
            p_values = entry["P"]
            for generator_id, generator in generators.items():
                output = self._to_float(p_values.get(generator_id), 0.0)
                if abs(output) <= self.TOLERANCE:
                    continue
                if output < generator["output_min"] - self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "generator_id": generator_id,
                            "output": output,
                            "output_min": generator["output_min"],
                            "output_max": generator["output_max"],
                            "reason": "below_min",
                        }
                    )
                elif output > generator["output_max"] + self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "generator_id": generator_id,
                            "output": output,
                            "output_min": generator["output_min"],
                            "output_max": generator["output_max"],
                            "reason": "above_max",
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "generator_output_bounds",
                f"generator output bound violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "generator_output_bounds", "all generator outputs are within bounds")

    def _check_generator_ramp_limits(
        self,
        generators: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        entries_by_t = {entry["t"]: entry for entry in self._schedule_entries(schedule_result)}
        missing_specs = self._missing_generator_fields(generators, ("ramp_up_rate", "ramp_down_rate", "initial_energy"))
        if missing_specs:
            report.add(
                "FAIL",
                "generator_ramp_limits",
                "cannot check generator ramp limits because processor_settings.generator is missing required fields",
                {"missing_fields": missing_specs},
            )
            return
        violations: list[dict[str, Any]] = []
        for generator_id, generator in generators.items():
            previous_output = generator["initial_energy"]
            for t in range(1, self.HORIZON + 1):
                p_values = entries_by_t.get(t, {}).get("P", {})
                current_output = self._to_float(p_values.get(generator_id), 0.0)
                ramp_up = current_output - previous_output
                ramp_down = previous_output - current_output
                if ramp_up > generator["ramp_up_rate"] + self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "generator_id": generator_id,
                            "previous_output": previous_output,
                            "current_output": current_output,
                            "ramp_up_rate": generator["ramp_up_rate"],
                            "ramp_down_rate": generator["ramp_down_rate"],
                            "reason": "ramp_up_violation",
                        }
                    )
                elif ramp_down > generator["ramp_down_rate"] + self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "generator_id": generator_id,
                            "previous_output": previous_output,
                            "current_output": current_output,
                            "ramp_up_rate": generator["ramp_up_rate"],
                            "ramp_down_rate": generator["ramp_down_rate"],
                            "reason": "ramp_down_violation",
                        }
                    )
                previous_output = current_output

        if violations:
            report.add(
                "FAIL",
                "generator_ramp_limits",
                f"generator ramp violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "generator_ramp_limits", "all generator ramp limits are satisfied")

    def _check_generator_min_output_ramp_feasibility(
        self,
        generators: dict[str, dict[str, float]],
        report: CheckReport,
    ) -> None:
        violations = [
            {
                "generator_id": generator_id,
                "output_min": generator["output_min"],
                "ramp_up_rate": generator["ramp_up_rate"],
            }
            for generator_id, generator in generators.items()
            if generator["output_min"] > generator["ramp_up_rate"] + self.TOLERANCE
        ]
        if violations:
            report.add(
                "FAIL",
                "generator_min_output_ramp_feasibility",
                f"generator output_min > ramp_up_rate violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add(
                "PASS",
                "generator_min_output_ramp_feasibility",
                "all generators satisfy output_min <= ramp_up_rate",
            )

    def _check_generator_min_up_time(
        self,
        generators: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        entries_by_t = {entry["t"]: entry for entry in self._schedule_entries(schedule_result)}
        violations: list[dict[str, Any]] = []

        for generator_id, generator in generators.items():
            states = self._generator_states(generator_id, entries_by_t)
            previous_on = self._initial_on(generator)
            min_up_time = int(generator["min_up_time"])
            if min_up_time <= 0:
                continue

            for t in range(1, self.HORIZON + 1):
                current_on = states[t]
                if current_on and not previous_on:
                    required_on_until = t + min_up_time - 1
                    check_until = min(required_on_until, self.HORIZON)
                    first_off_t = self._first_state_change(states, t, check_until, expected_on=True)
                    if first_off_t is not None:
                        violations.append(
                            {
                                "generator_id": generator_id,
                                "startup_t": t,
                                "min_up_time": min_up_time,
                                "required_on_until": required_on_until,
                                "first_off_t": first_off_t,
                            }
                        )
                previous_on = current_on

        if violations:
            report.add(
                "FAIL",
                "generator_min_up_time",
                f"generator min up time violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "generator_min_up_time", "all generator min up time constraints are satisfied")

    def _check_generator_min_down_time(
        self,
        generators: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        entries_by_t = {entry["t"]: entry for entry in self._schedule_entries(schedule_result)}
        violations: list[dict[str, Any]] = []

        for generator_id, generator in generators.items():
            states = self._generator_states(generator_id, entries_by_t)
            previous_on = self._initial_on(generator)
            min_down_time = int(generator["min_down_time"])
            if min_down_time <= 0:
                continue

            for t in range(1, self.HORIZON + 1):
                current_on = states[t]
                if not current_on and previous_on:
                    required_off_until = t + min_down_time - 1
                    check_until = min(required_off_until, self.HORIZON)
                    first_on_t = self._first_state_change(states, t, check_until, expected_on=False)
                    if first_on_t is not None:
                        violations.append(
                            {
                                "generator_id": generator_id,
                                "shutdown_t": t,
                                "min_down_time": min_down_time,
                                "required_off_until": required_off_until,
                                "first_on_t": first_on_t,
                            }
                        )
                previous_on = current_on

        if violations:
            report.add(
                "FAIL",
                "generator_min_down_time",
                f"generator min down time violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "generator_min_down_time", "all generator min down time constraints are satisfied")

    def _check_generator_initial_on_time(
        self,
        generators: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        entries_by_t = {entry["t"]: entry for entry in self._schedule_entries(schedule_result)}
        violations: list[dict[str, Any]] = []

        for generator_id, generator in generators.items():
            if not self._initial_on(generator):
                continue
            min_up_time = int(generator["min_up_time"])
            initial_on_time = generator["initial_on_time"]
            remaining = int(max(0, min_up_time - initial_on_time))
            if remaining <= 0:
                continue
            states = self._generator_states(generator_id, entries_by_t)
            required_on_until = min(remaining, self.HORIZON)
            first_off_t = self._first_state_change(states, 1, required_on_until, expected_on=True)
            if first_off_t is not None:
                violations.append(
                    {
                        "generator_id": generator_id,
                        "initial_on_time": initial_on_time,
                        "min_up_time": min_up_time,
                        "required_on_until": required_on_until,
                        "first_off_t": first_off_t,
                    }
                )

        if violations:
            report.add(
                "FAIL",
                "generator_initial_on_time",
                f"generator initial on time violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "generator_initial_on_time", "all initial on time constraints are satisfied")

    def _check_generator_initial_off_time(
        self,
        generators: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        entries_by_t = {entry["t"]: entry for entry in self._schedule_entries(schedule_result)}
        violations: list[dict[str, Any]] = []

        for generator_id, generator in generators.items():
            if self._initial_on(generator):
                continue
            min_down_time = int(generator["min_down_time"])
            initial_off_time = generator["initial_off_time"]
            remaining = int(max(0, min_down_time - initial_off_time))
            if remaining <= 0:
                continue
            states = self._generator_states(generator_id, entries_by_t)
            required_off_until = min(remaining, self.HORIZON)
            first_on_t = self._first_state_change(states, 1, required_off_until, expected_on=False)
            if first_on_t is not None:
                violations.append(
                    {
                        "generator_id": generator_id,
                        "initial_off_time": initial_off_time,
                        "min_down_time": min_down_time,
                        "required_off_until": required_off_until,
                        "first_on_t": first_on_t,
                    }
                )

        if violations:
            report.add(
                "FAIL",
                "generator_initial_off_time",
                f"generator initial off time violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "generator_initial_off_time", "all initial off time constraints are satisfied")

    def _check_renewable_output_upper_bound(
        self,
        capacities: dict[str, float],
        forecasts: dict[tuple[str, int], float],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            t = entry["t"]
            p_values = entry["P"]
            for renewable_id, capacity in capacities.items():
                forecast = forecasts.get((renewable_id, t))
                if forecast is None:
                    violations.append(
                        {
                            "t": t,
                            "renewable_id": renewable_id,
                            "reason": "missing_forecast",
                        }
                    )
                    continue
                output = self._to_float(p_values.get(renewable_id), 0.0)
                max_allowed = capacity * forecast
                if output < -self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "renewable_id": renewable_id,
                            "output": output,
                            "capacity": capacity,
                            "forecast": forecast,
                            "max_allowed": max_allowed,
                            "reason": "negative_output",
                        }
                    )
                elif output > max_allowed + self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "renewable_id": renewable_id,
                            "output": output,
                            "capacity": capacity,
                            "forecast": forecast,
                            "max_allowed": max_allowed,
                            "reason": "above_forecast",
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "renewable_output_upper_bound",
                f"renewable output upper-bound violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "renewable_output_upper_bound", "all renewable outputs are within forecast bounds")

    def _check_storage_discharge_limit(
        self,
        storages: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        if not storages:
            report.add("PASS", "storage_discharge_limit", "no storage devices found")
            return

        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            for storage_id, storage in storages.items():
                discharge = self._to_float(entry["P"].get(storage_id), 0.0)
                if discharge < -self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "discharge": discharge,
                            "discharge_max": storage["discharge_max"],
                            "reason": "negative_discharge",
                        }
                    )
                elif discharge > storage["discharge_max"] + self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "discharge": discharge,
                            "discharge_max": storage["discharge_max"],
                            "reason": "above_discharge_max",
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "storage_discharge_limit",
                f"storage discharge limit violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "storage_discharge_limit", "all storage discharge limits are satisfied")

    def _check_storage_charge_limit(
        self,
        storages: dict[str, dict[str, float]],
        charging_job_targets: dict[str, str],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        if not storages:
            report.add("PASS", "storage_charge_limit", "no storage devices found")
            return

        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            charges, job_ids = self._storage_charges(entry, charging_job_targets)
            for storage_id, storage in storages.items():
                charge = charges.get(storage_id, 0.0)
                if charge < -self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "charge": charge,
                            "charge_max": storage["charge_max"],
                            "charging_jobs": job_ids.get(storage_id, []),
                            "reason": "negative_charge",
                        }
                    )
                elif charge > storage["charge_max"] + self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "charge": charge,
                            "charge_max": storage["charge_max"],
                            "charging_jobs": job_ids.get(storage_id, []),
                            "reason": "above_charge_max",
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "storage_charge_limit",
                f"storage charge limit violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "storage_charge_limit", "all storage charge limits are satisfied")

    def _check_storage_soc_transition(
        self,
        storages: dict[str, dict[str, float]],
        charging_job_targets: dict[str, str],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        if not storages:
            report.add("PASS", "storage_soc_transition", "no storage devices found")
            return

        entries_by_t = {entry["t"]: entry for entry in self._schedule_entries(schedule_result)}
        violations: list[dict[str, Any]] = []
        for storage_id, storage in storages.items():
            previous_soc = storage["soc_init"]
            for t in range(1, self.HORIZON + 1):
                entry = entries_by_t.get(t, {"P": {}, "k": {}, "soc": {}})
                charges, _job_ids = self._storage_charges(entry, charging_job_targets)
                charge = charges.get(storage_id, 0.0)
                discharge = self._to_float(entry["P"].get(storage_id), 0.0)
                soc_values = entry.get("soc") if isinstance(entry.get("soc"), dict) else {}
                if storage_id not in soc_values:
                    violations.append(
                        {
                            "t": t,
                            "storage_id": storage_id,
                            "previous_soc": previous_soc,
                            "charge": charge,
                            "discharge": discharge,
                            "expected_soc": previous_soc + charge - discharge,
                            "actual_soc": None,
                            "difference": None,
                        }
                    )
                    previous_soc = 0.0
                    continue
                actual_soc = self._to_float(soc_values.get(storage_id), 0.0)
                expected_soc = previous_soc + charge - discharge
                difference = actual_soc - expected_soc
                if abs(difference) > self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "storage_id": storage_id,
                            "previous_soc": previous_soc,
                            "charge": charge,
                            "discharge": discharge,
                            "expected_soc": expected_soc,
                            "actual_soc": actual_soc,
                            "difference": difference,
                        }
                    )
                previous_soc = actual_soc

        if violations:
            report.add(
                "FAIL",
                "storage_soc_transition",
                f"storage SOC transition violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "storage_soc_transition", "all storage SOC transitions are satisfied")

    def _check_storage_soc_bounds(
        self,
        storages: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        if not storages:
            report.add("PASS", "storage_soc_bounds", "no storage devices found")
            return

        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            soc_values = entry.get("soc") if isinstance(entry.get("soc"), dict) else {}
            for storage_id, storage in storages.items():
                if storage_id not in soc_values:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "soc": None,
                            "soc_min": storage["soc_min"],
                            "soc_max": storage["soc_max"],
                            "reason": "missing_soc",
                        }
                    )
                    continue
                soc = self._to_float(soc_values.get(storage_id), 0.0)
                if soc < storage["soc_min"] - self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "soc": soc,
                            "soc_min": storage["soc_min"],
                            "soc_max": storage["soc_max"],
                            "reason": "below_soc_min",
                        }
                    )
                elif soc > storage["soc_max"] + self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "soc": soc,
                            "soc_min": storage["soc_min"],
                            "soc_max": storage["soc_max"],
                            "reason": "above_soc_max",
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "storage_soc_bounds",
                f"storage SOC bound violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "storage_soc_bounds", "all storage SOC values are within bounds")

    def _check_storage_discharge_available_energy(
        self,
        storages: dict[str, dict[str, float]],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        if not storages:
            report.add("PASS", "storage_discharge_available_energy", "no storage devices found")
            return

        entries_by_t = {entry["t"]: entry for entry in self._schedule_entries(schedule_result)}
        violations: list[dict[str, Any]] = []
        for storage_id, storage in storages.items():
            previous_soc = storage["soc_init"]
            for t in range(1, self.HORIZON + 1):
                entry = entries_by_t.get(t, {"P": {}, "soc": {}})
                discharge = self._to_float(entry["P"].get(storage_id), 0.0)
                available_discharge = previous_soc - storage["soc_min"]
                if discharge > available_discharge + self.TOLERANCE:
                    violations.append(
                        {
                            "t": t,
                            "storage_id": storage_id,
                            "previous_soc": previous_soc,
                            "soc_min": storage["soc_min"],
                            "available_discharge": available_discharge,
                            "discharge": discharge,
                        }
                    )
                soc_values = entry.get("soc") if isinstance(entry.get("soc"), dict) else {}
                previous_soc = self._to_float(soc_values.get(storage_id), 0.0)

        if violations:
            report.add(
                "FAIL",
                "storage_discharge_available_energy",
                f"storage available discharge violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add(
                "PASS",
                "storage_discharge_available_energy",
                "all storage discharge values fit available energy",
            )

    def _check_storage_no_simultaneous_charge_discharge(
        self,
        storages: dict[str, dict[str, float]],
        charging_job_targets: dict[str, str],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        if not storages:
            report.add("PASS", "storage_no_simultaneous_charge_discharge", "no storage devices found")
            return

        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            charges, _job_ids = self._storage_charges(entry, charging_job_targets)
            for storage_id in storages:
                charge = charges.get(storage_id, 0.0)
                discharge = self._to_float(entry["P"].get(storage_id), 0.0)
                if charge > self.TOLERANCE and discharge > self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "storage_id": storage_id,
                            "charge": charge,
                            "discharge": discharge,
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "storage_no_simultaneous_charge_discharge",
                f"simultaneous charge/discharge violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add(
                "PASS",
                "storage_no_simultaneous_charge_discharge",
                "no storage charges and discharges simultaneously",
            )

    def _check_schedule_device_fields(
        self,
        device_ids: set[str],
        storage_ids: set[str],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            t = entry["t"]
            p_values = entry["P"]
            p_ids = {device_id for device_id in p_values if isinstance(device_id, str)}
            unknown_p = sorted(p_ids - device_ids)
            if unknown_p:
                violations.append({"t": t, "field": "P", "reason": "unknown_devices", "device_ids": unknown_p})

            soc_values = entry.get("soc") if isinstance(entry.get("soc"), dict) else {}
            soc_ids = {storage_id for storage_id in soc_values if isinstance(storage_id, str)}
            missing_soc = sorted(storage_ids - soc_ids)
            unknown_soc = sorted(soc_ids - storage_ids)
            if missing_soc:
                violations.append({"t": t, "field": "soc", "reason": "missing_storage_devices", "storage_ids": missing_soc})
            if unknown_soc:
                violations.append({"t": t, "field": "soc", "reason": "unknown_storage_devices", "storage_ids": unknown_soc})

            for job_id, allocation in entry["k"].items():
                if not isinstance(allocation, dict):
                    continue
                allocation_ids = {device_id for device_id in allocation if isinstance(device_id, str)}
                unknown_allocation = sorted(allocation_ids - device_ids)
                if unknown_allocation:
                    violations.append(
                        {
                            "t": t,
                            "field": "k",
                            "job_id": job_id,
                            "reason": "unknown_allocation_devices",
                            "device_ids": unknown_allocation,
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "schedule_device_fields",
                f"schedule_result device field violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "schedule_device_fields", "schedule_result uses only configured devices")

    def _check_charging_source_validity(
        self,
        generator_ids: set[str],
        renewable_ids: set[str],
        charging_job_targets: dict[str, str],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        allowed_sources = generator_ids | renewable_ids
        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            for job_id, allocation in entry["k"].items():
                target_storage = self._target_storage_for_charging_job(job_id, charging_job_targets)
                if target_storage is None or not isinstance(allocation, dict):
                    continue
                for source_id, energy in allocation.items():
                    energy_value = self._to_float(energy, 0.0)
                    if energy_value <= self.TOLERANCE:
                        continue
                    if source_id not in allowed_sources:
                        violations.append(
                            {
                                "t": entry["t"],
                                "charging_job_id": job_id,
                                "target_storage": target_storage,
                                "invalid_source": source_id,
                                "energy": energy_value,
                            }
                        )

        if violations:
            report.add(
                "FAIL",
                "charging_source_validity",
                f"invalid charging source violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "charging_source_validity", "all charging jobs use valid source devices")

    def _check_device_supply_capacity(
        self,
        storages: dict[str, dict[str, float]],
        charging_job_targets: dict[str, str],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            supplied_by_device: dict[str, float] = {}
            for job_id, allocation in entry["k"].items():
                if not isinstance(allocation, dict):
                    continue
                target_storage = self._target_storage_for_charging_job(job_id, charging_job_targets)
                for device_id, energy in allocation.items():
                    if not isinstance(device_id, str):
                        continue
                    energy_value = self._to_float(energy, 0.0)
                    supplied_by_device[device_id] = supplied_by_device.get(device_id, 0.0) + energy_value
                    if target_storage is not None and device_id in storages and energy_value > self.TOLERANCE:
                        violations.append(
                            {
                                "t": entry["t"],
                                "device_id": device_id,
                                "charging_job_id": job_id,
                                "energy": energy_value,
                                "reason": "storage_supplies_charging_job",
                            }
                        )

            for device_id, supplied in supplied_by_device.items():
                output = self._to_float(entry["P"].get(device_id), 0.0)
                if supplied > output + self.TOLERANCE:
                    violations.append(
                        {
                            "t": entry["t"],
                            "device_id": device_id,
                            "supplied": supplied,
                            "output": output,
                            "reason": "supply_exceeds_device_output",
                        }
                    )

        if violations:
            report.add(
                "FAIL",
                "device_supply_capacity",
                f"device supply capacity violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "device_supply_capacity", "all device supplies fit output capacity")

    def _check_sell_non_negative(self, schedule_result: list[Any] | None, report: CheckReport) -> None:
        violations = [
            {"t": entry["t"], "sell": self._to_float(entry.get("sell"), 0.0)}
            for entry in self._schedule_entries(schedule_result)
            if self._to_float(entry.get("sell"), 0.0) < -self.TOLERANCE
        ]
        if violations:
            report.add(
                "FAIL",
                "sell_non_negative",
                f"negative sell values = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "sell_non_negative", "all sell values are non-negative")

    def _check_hourly_energy_balance(
        self,
        charging_jobs: set[str],
        schedule_result: list[Any] | None,
        report: CheckReport,
    ) -> None:
        violations: list[dict[str, Any]] = []
        for entry in self._schedule_entries(schedule_result):
            p_values = entry["P"]
            k_values = entry["k"]
            total_generation = sum(self._to_float(value, 0.0) for value in p_values.values())
            external_job_demand = 0.0
            charging_demand = 0.0
            for job_id, allocation in k_values.items():
                demand = self._sum_allocation(allocation)
                if self._is_charging_job(job_id, charging_jobs):
                    charging_demand += demand
                else:
                    external_job_demand += demand

            sell = self._to_float(entry.get("sell"), 0.0)
            rhs = external_job_demand + charging_demand + sell
            difference = total_generation - rhs
            if abs(difference) > self.TOLERANCE:
                violations.append(
                    {
                        "t": entry["t"],
                        "total_generation": total_generation,
                        "external_job_demand": external_job_demand,
                        "charging_demand": charging_demand,
                        "sell": sell,
                        "rhs": rhs,
                        "difference": difference,
                    }
                )

        if violations:
            report.add(
                "FAIL",
                "hourly_energy_balance",
                f"hourly energy balance violations = {len(violations)}",
                self._sample_details(violations),
            )
        else:
            report.add("PASS", "hourly_energy_balance", "all hourly energy balances are satisfied")

    def _schedule_entries(self, schedule_result: list[Any] | None) -> list[dict[str, Any]]:
        if not isinstance(schedule_result, list):
            return []
        entries: list[dict[str, Any]] = []
        for raw in schedule_result:
            if not isinstance(raw, dict):
                continue
            t = self._to_int(raw.get("t"))
            if t is None:
                continue
            entries.append(
                {
                    **raw,
                    "t": t,
                    "P": raw.get("P") if isinstance(raw.get("P"), dict) else {},
                    "k": raw.get("k") if isinstance(raw.get("k"), dict) else {},
                }
            )
        return entries

    def _is_charging_job(self, job_id: Any, charging_jobs: set[str]) -> bool:
        return isinstance(job_id, str) and (job_id in charging_jobs or job_id.endswith("_chg"))

    def _storage_charges(
        self,
        entry: dict[str, Any],
        charging_job_targets: dict[str, str],
    ) -> tuple[dict[str, float], dict[str, list[str]]]:
        charges: dict[str, float] = {}
        job_ids: dict[str, list[str]] = {}
        for job_id, allocation in entry["k"].items():
            target_storage = self._target_storage_for_charging_job(job_id, charging_job_targets)
            if target_storage is None:
                continue
            charges[target_storage] = charges.get(target_storage, 0.0) + self._sum_allocation(allocation)
            job_ids.setdefault(target_storage, []).append(job_id)
        return charges, job_ids

    def _target_storage_for_charging_job(
        self,
        job_id: Any,
        charging_job_targets: dict[str, str],
    ) -> str | None:
        if not isinstance(job_id, str):
            return None
        if job_id in charging_job_targets:
            return charging_job_targets[job_id]
        if job_id.endswith("_chg"):
            return job_id.removesuffix("_chg")
        return None

    def _generator_states(self, generator_id: str, entries_by_t: dict[int, dict[str, Any]]) -> dict[int, bool]:
        states: dict[int, bool] = {}
        for t in range(1, self.HORIZON + 1):
            p_values = entries_by_t.get(t, {}).get("P", {})
            output = self._to_float(p_values.get(generator_id), 0.0)
            states[t] = output > self.TOLERANCE
        return states

    def _initial_on(self, generator: dict[str, float]) -> bool:
        return generator["initial_energy"] > self.TOLERANCE

    def _first_state_change(
        self,
        states: dict[int, bool],
        start_t: int,
        end_t: int,
        *,
        expected_on: bool,
    ) -> int | None:
        for t in range(start_t, end_t + 1):
            if states[t] != expected_on:
                return t
        return None

    def _sum_allocation(self, allocation: Any) -> float:
        if isinstance(allocation, dict):
            return sum(self._to_float(value, 0.0) for value in allocation.values())
        return self._to_float(allocation, 0.0)

    def _sample_details(self, records: list[Any]) -> dict[str, Any]:
        return {"count": len(records), "samples": records[: self.SAMPLE_LIMIT]}

    def _missing_generator_fields(
        self,
        generators: dict[str, dict[str, Any]],
        required_fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for generator_id, generator in generators.items():
            generator_missing = set(generator.get("_missing_fields", []))
            fields = [field_name for field_name in required_fields if field_name in generator_missing]
            if fields:
                missing.append({"generator_id": generator_id, "missing_fields": fields})
        return missing

    def _to_float(self, value: Any, default: float) -> float:
        if isinstance(value, bool):
            return default
        if isinstance(value, int | float):
            return float(value)
        return default

    def _to_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None
