"""Validate downloaded human responses before unblinding and aggregating them."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

RATINGS = {"Flow", "Returning sections", "Ending", "Would use this"}


def summarize(documents, answer_key):
    participants, preferences, scores, incomplete = set(), Counter(), defaultdict(list), 0
    pairs = defaultdict(set)
    for identifier, entry in answer_key.items():
        pairs[entry["pair"]].add(identifier)
    if not pairs or any(len(ids) != 2 for ids in pairs.values()):
        raise ValueError("Answer key must contain two distinct clips per pair")
    for document in documents:
        participant = document.get("participant", "").strip()
        if document.get("version") != 1 or not participant or participant in participants:
            raise ValueError("Unsupported response, missing participant or duplicate participant")
        participants.add(participant)
        responses = document.get("responses", [])
        if len(responses) != len(pairs) or {r["pair"] for r in responses} != set(pairs):
            raise ValueError("Missing, duplicate or unknown pair")
        for response in responses:
            variants = response["variants"]
            if (len(variants) != 2 or {v["id"] for v in variants} != pairs[response["pair"]]
                    or {v["label"] for v in variants} != {"A", "B"}):
                raise ValueError("Clip IDs or A/B labels do not match this answer key")
            preference = response["preference"]
            if preference not in {"A", "B", "Tie", "Neither"}:
                raise ValueError("Missing preference")
            for variant in variants:
                ratings = variant["ratings"]
                if set(ratings) != RATINGS or any(type(n) is not int or not 1 <= n <= 5 for n in ratings.values()):
                    raise ValueError("Every rating must be an integer from 1 to 5")
                if type(variant.get("listenedToEnd")) is not bool:
                    raise ValueError("Missing listening completion flag")
                incomplete += not variant["listenedToEnd"]
                arm = answer_key[variant["id"]]["arm"]
                for name, value in ratings.items():
                    scores[f"{arm}/{name}"].append(value)
                if preference == variant["label"]:
                    preferences[arm] += 1
            if preference in {"Tie", "Neither"}:
                preferences[preference] += 1
    return dict(participants=len(participants), pairedComparisons=sum(preferences.values()),
                preferences=dict(preferences), clipsNotPlayedToEnd=incomplete,
                ratings={key: dict(n=len(values), mean=statistics.mean(values), median=statistics.median(values))
                         for key, values in sorted(scores.items())},
                limitation="Exploratory convenience sample; pairs from the same person are not independent. "
                           "Playback completion does not establish attention or musical expertise. "
                           "This does not measure editing time or prove musical superiority.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--responses", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.out.is_absolute() or args.out.exists():
        parser.error("Use a new absolute report path")
    report = summarize([json.loads(path.read_text()) for path in args.responses],
                       json.loads(args.private_key.read_text()))
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Validated {report['participants']} participants and {report['pairedComparisons']} comparisons")


if __name__ == "__main__":
    main()
