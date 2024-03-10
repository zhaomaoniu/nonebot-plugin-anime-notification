from rapidfuzz import process, fuzz


def fuzzy_match(query: str, d: dict, n: int) -> list:
    matched_keys = []
    print(d)
    for key, value in d.items():
        matches = process.extract(query, value, limit=n, scorer=fuzz.ratio)
        for match in matches:
            matched_keys.append(
                {
                    "id": key,
                    "match": match[0],
                    "score": match[1],
                }
            )
    matched_keys.sort(key=lambda x: x["score"], reverse=True)
    return matched_keys[:n]
