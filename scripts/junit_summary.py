#!/usr/bin/env python3
"""Turn a pytest JUnit XML file into a Markdown table (for the GitHub job summary)."""
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
total, failed = int(suite.get("tests")), int(suite.get("failures")) + int(suite.get("errors"))
skipped = int(suite.get("skipped"))
icon = "❌" if failed else "✅"
print(f"### {icon} Unit tests: {total - failed - skipped} passed, {failed} failed, {skipped} skipped\n")
if failed:
    print("| Failed test | Message |\n|---|---|")
    for case in suite.iter("testcase"):
        for bad in list(case.findall("failure")) + list(case.findall("error")):
            msg = (bad.get("message") or "").splitlines()[0][:150].replace("|", "\\|")
            print(f"| `{case.get('classname')}::{case.get('name')}` | {msg} |")
