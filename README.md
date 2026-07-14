# SSP Model Rocket Compliance RAG

## Purpose

This project creates a governed retrieval-augmented generation target that supports preliminary compliance checks of model rockets and proposed launches.

The system will compare structured rocket and launch information against authoritative FAA and National Association of Rocketry sources.

## Authoritative Sources

1. FAA 14 CFR Part 101, Subpart C—Amateur Rockets
2. NAR Model Rocket Safety Code

## Planned Workflow

1. Preserve the authoritative source.
2. Document its provenance, version, authority, and permissions.
3. Divide the source into citation-preserving chunks.
4. Convert objective requirements into machine-checkable rules.
5. Accept structured information about a rocket and launch.
6. Retrieve relevant source provisions.
7. Produce a cited preliminary compliance report.

## Compliance Results

- `PASS`
- `FAIL`
- `INSUFFICIENT_INFORMATION`
- `NOT_APPLICABLE`
- `HUMAN_REVIEW_REQUIRED`

## Limitations

This project does not issue FAA authorization and does not replace review by the FAA, a range safety officer, a launch-site operator, or another qualified human reviewer.
