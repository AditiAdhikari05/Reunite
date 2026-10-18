# End-to-end results (synthetic data)

Held-out reports (never used for training): **117**, each searched against **595** found people.

| Method | Right person ranked 1st | In top 5 |
|---|---|---|
| Keyword search on the description | 7% | 19% |
| Hand-weighted rules | 57% | 75% |
| **Our learned scorer (deployed)** | **73%** | **92%** |

Top 3: 91%. Top 10: 98%. Guessing would put the right person first 0.17% of the time.

Human-review flag (score >= 0.89): flags 59% of reports; the flagged top pick is right 94% of the time; false alarms on reports with no real match: 5%. A person still confirms every match.

## What each kind of information is worth (removed one at a time)

| Removed | Right person ranked 1st | In top 5 |
|---|---|---|
| without demographics (gender, age, height) | 54% | 73% |
| without appearance text (hair, clothing, marks) | 33% | 53% |
| without free-text description | 72% | 92% |
| without place and time | 70% | 90% |

## Live walk-through (HTTP, as the front end does it)

**Demo case 2: male, 49-51, last seen Textile Mill Colony**: true match ranked #1, score 89, runner-ups [80, 32, 16]

- matched: Gender matches (male)
- matched: Age ranges overlap (49-51 vs 44-49; found age is an estimate)
- matched: Height 173 cm vs 178 cm
- matched: Hair similar (very short dark brown hair vs very short dark)
- differs: Clothing differs (dark hooded sweatshirt, black jeans, yellow flip-flops vs orange anorak, violet shorts)
- matched: Distinguishing marks in both (limp in left leg; nose piercing vs walks with a limp; pierced nose)
- matched: Found 7 km from last seen place, 28 hours later

**Demo case 3: female, 13-14, last seen Textile Mill Colony**: true match ranked #1, score 99, runner-ups [24, 21, 16]

- matched: Gender matches (female)
- matched: Age ranges overlap (13-14 vs 10-14; found age is an estimate)
- matched: Height 164 cm vs 170 cm
- matched: Clothing overlaps (navy rain jacket, grey shorts, brown running shoes vs gray shorts, bright orange rain jacket)
- matched: Distinguishing marks in both (missing front tooth vs front tooth missing)
- differs: Found 11 km from last seen place, 1 hours later

**Demo case 5: other, 58-62, last seen Water Tower Square**: true match ranked #1, score 99, runner-ups [15, 7, 4]

- matched: Gender matches (other)
- matched: Age ranges overlap (58-62 vs 52-63; found age is an estimate)
- matched: Height 166 cm vs 168 cm
- matched: Clothing overlaps (blue jumper, charcoal shorts, black sneakers vs blue sweater, grey shorts, black sneakers)
- matched: Distinguishing marks in both (scar above left eyebrow; mole on left cheek vs scar on forehead; mole on face)
- matched: Found 5 km from last seen place, 35 hours later

Checks passed: 31, failed: 0.

Caveats: synthetic data; scores are ranking scores, not probabilities; the found-time window in the generator is simpler than real life.