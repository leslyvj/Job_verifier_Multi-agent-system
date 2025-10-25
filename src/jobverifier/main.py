from __future__ import annotations

from .orchestrator import ParentOrchestrator


def main() -> None:
    url = input("Enter job posting URL: ").strip()
    orchestrator = ParentOrchestrator()
    result = orchestrator.process_job(url)
    print(result)


if __name__ == "__main__":
    main()
