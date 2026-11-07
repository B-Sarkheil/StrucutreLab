# -*- coding: utf-8 -*-
"""Auto Design - step 10: standardizing ("typifying") the sections of a member (no Qt, no SAP).

Goal: replace the sections used by a group of frames with at most K
different sections, so that the weight increase is as small as possible
(dynamic programming, table filling).

Assumptions:
  - a heavier section (bigger area) is an allowed replacement of a lighter
    one; the weight of a frame is proportional to area x length (same
    density inside one material);
  - sections of different materials are never merged (they are sorted by
    material first, and a type never spans two materials);
  - a type is a contiguous range in the list sorted by (material, area);
    every section of the range is replaced by the LARGEST one of the range
    (the optimal choice for a fixed range: the cheapest replacement that is
    still allowed for all of them).

Reviewed 2026-11-04: the recurrence is the classic optimal 1-D partition,
O(K * n^2) in time (n = number of different sections), correct for ranges
whose cost is "upgrade everything to the last element".

Functions:
  typify(sections, K)     one group of frames (one role) -> K types
  typify_member(...)      all roles of one member, returns the new genes
"""
from __future__ import annotations

from dataclasses import dataclass

INF = float("inf")


def typify(sections, K):
    """
    sections : list of (name, area, length) or (name, area, length, material).
               One row per frame or per section; rows with the same name are
               summed (their areas and materials must agree).
    K        : maximum number of types (limited to the number of sections).

    Returns a dict:
      groups           : list of types (type, members, extra_volume)
      mapping          : old section -> new section (the type)
      extra_volume     : weight increase (same unit as area * length)
      original_volume  : original volume
      increase_percent : weight increase in percent (independent of density)
    To get kg, multiply extra_volume by the density and the unit factor.
    """
    # 1) total length of every unique section
    agg = {}
    for row in sections:
        name, area, length = row[0], row[1], row[2]
        material = row[3] if len(row) > 3 else ""

        if area <= 0:
            raise ValueError(f"Section '{name}' has a non-positive area ({area})")

        if name in agg:
            if abs(agg[name][0] - area) > 1e-9 * max(1.0, abs(area)):
                raise ValueError(f"Section '{name}' has inconsistent areas")
            if agg[name][2] != material:
                raise ValueError(f"Section '{name}' has inconsistent materials")
            agg[name][1] += length
        else:
            agg[name] = [area, length, material]

    # 2) sort by material, then by area (name breaks ties: deterministic)
    items = sorted(
        ((n, a, m, mat) for n, (a, m, mat) in agg.items()),
        key=lambda x: (x[3], x[1], x[0]),
    )
    n = len(items)
    if n == 0:
        raise ValueError("sections is empty")
    K = max(1, min(K, n))

    # 3) cumulative sums, so the cost of a range is O(1)
    M = [0.0] * (n + 1)   # cumulative length
    W = [0.0] * (n + 1)   # cumulative length x area
    for t, (_, a, m, _mat) in enumerate(items, 1):
        M[t] = M[t - 1] + m
        W[t] = W[t - 1] + m * a

    def cost(i, j):
        """Extra volume of the range i..j (1-based) when all become section j.
        A range that mixes materials is not allowed (infinite cost)."""
        if items[i - 1][3] != items[j - 1][3]:
            return INF
        return items[j - 1][1] * (M[j] - M[i - 1]) - (W[j] - W[i - 1])

    # 4) DP: D[k][j] = least extra volume for the first j sections in k types
    D = [[INF] * (n + 1) for _ in range(K + 1)]
    P = [[0] * (n + 1) for _ in range(K + 1)]
    D[0][0] = 0.0
    for k in range(1, K + 1):
        for j in range(k, n + 1):
            for i in range(k, j + 1):
                v = D[k - 1][i - 1] + cost(i, j)
                if v < D[k][j]:
                    D[k][j], P[k][j] = v, i

    if D[K][n] == INF:
        materials = len({it[3] for it in items})
        raise ValueError(
            f"{K} type(s) are not enough: the sections use {materials} different "
            "materials and sections of different materials cannot be merged."
        )

    # 5) trace back
    ranges, j = [], n
    for k in range(K, 0, -1):
        i = P[k][j]
        ranges.append((i, j))
        j = i - 1
    ranges.reverse()

    groups = [{
        "type": items[j - 1][0],
        "members": [items[t - 1][0] for t in range(i, j + 1)],
        "extra_volume": cost(i, j),
    } for i, j in ranges]

    return {
        "groups": groups,
        "mapping": {m: g["type"] for g in groups for m in g["members"]},
        "extra_volume": D[K][n],
        "original_volume": W[n],
        "increase_percent": 100 * D[K][n] / W[n] if W[n] else 0.0,
    }


@dataclass(frozen=True)
class TypifyOutcome:
    """Result of `typify_member`."""

    genes: dict[str, str]  # frame -> new section (all frames)
    byRole: dict[str, dict]  # role -> result of `typify` (roles in use only)
    extraVolume: float
    originalVolume: float
    increasePercent: float  # of the weight of the frames
    changedFrames: int  # frames whose section is different now


def typify_member(
    genes: dict[str, str],
    roles: dict[str, str],
    counts: dict[str, int],
    areas: dict[str, float],
    materials: dict[str, str],
    lengths: dict[str, float],
) -> TypifyOutcome:
    """Typify every role of one member separately.

    genes     : frame -> section of the member
    roles     : frame -> role (column, beam, ...)
    counts    : role -> number of types wanted (0 or missing: role not used)
    areas     : section -> cross-section area
    materials : section -> material type (sections of different materials are never merged)
    lengths   : frame -> length (same length unit for all frames)
    """
    problems = []

    no_area = sorted({s for s in genes.values() if s not in areas})
    if no_area:
        problems.append("no area found for the section(s): " + ", ".join(no_area))

    no_length = sorted(f for f in genes if f not in lengths)
    if no_length:
        shown = ", ".join(no_length[:10])
        problems.append(f"no length for {len(no_length)} frame(s): {shown}")

    if problems:
        raise ValueError("; ".join(problems) + ".")

    by_role: dict[str, dict] = {}
    extra = original = 0.0

    for role in dict.fromkeys(roles[f] for f in genes):
        wanted = counts.get(role, 0)
        rows = [
            (section, areas[section], lengths[frame], materials.get(section, ""))
            for frame, section in genes.items()
            if roles[frame] == role
        ]

        if wanted < 1 or not rows:
            continue

        result = typify(rows, wanted)
        by_role[role] = result
        extra += result["extra_volume"]
        original += result["original_volume"]

    new_genes = {
        frame: by_role[roles[frame]]["mapping"][section] if roles[frame] in by_role else section
        for frame, section in genes.items()
    }

    return TypifyOutcome(
        genes=new_genes,
        byRole=by_role,
        extraVolume=extra,
        originalVolume=original,
        increasePercent=100.0 * extra / original if original else 0.0,
        changedFrames=sum(new_genes[f] != genes[f] for f in genes),
    )
