"""Supply-chain validation checks over dependency audit artifacts."""

import json
import re
from pathlib import Path


def _load_vuln_report() -> dict:
    report_path = Path("vulnerabilities.json")
    assert report_path.exists(), "vulnerabilities.json audit artifact is missing"
    return json.loads(report_path.read_text(encoding="utf-8"))


def test_vulnerability_report_has_expected_schema() -> None:
    report = _load_vuln_report()
    assert "dependencies" in report
    assert isinstance(report["dependencies"], list)


def test_no_unapproved_cves_in_audit_report() -> None:
    report = _load_vuln_report()
    approved_cves = {"CVE-2024-23342"}  # accepted risk for python-ecdsa timing side-channel scope

    found_cves = set()
    for dep in report["dependencies"]:
        for vuln in dep.get("vulns", []):
            vuln_id = vuln.get("id")
            if vuln_id:
                found_cves.add(vuln_id)

    unexpected = sorted(found_cves - approved_cves)
    assert not unexpected, f"Unexpected CVEs found: {unexpected}"


def test_cve_identifier_format_is_valid() -> None:
    report = _load_vuln_report()
    pattern = re.compile(r"^CVE-\d{4}-\d{4,}$")

    for dep in report["dependencies"]:
        for vuln in dep.get("vulns", []):
            vuln_id = vuln.get("id", "")
            assert pattern.match(vuln_id), f"Invalid CVE format: {vuln_id}"
