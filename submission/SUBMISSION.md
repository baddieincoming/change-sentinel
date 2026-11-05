# Submission form answers

## Problem Statement

The Change Sentinel: watch a district from orbit and produce case files, not curiosities. Our build detects new illegal stone quarries in Nuh district, Haryana, from free Sentinel-2 imagery.

## Describe the problem you are trying to solve

Illegal quarrying is visible in free satellite imagery long before anyone complains, but nobody watches continuously. Manual image comparison doesn't scale beyond a few villages. Naive change detection drowns in false alarms from clouds, shadows, the monsoon and harvests. Commercial monitoring is priced for corporate customers, not a district office or a citizen group. And an alert with no jurisdiction, no area and no before-and-after view isn't something an officer can act on.

We chose one change class, new open-cast stone quarries, in one district, Nuh in Haryana. The Supreme Court suspended all mining in the Aravalli hills of Faridabad, Gurugram and Nuh on 8 May 2009, so a new pit in Nuh's hills is presumptively unauthorised. Even so, illegal mining there has continued for years. The national Mining Surveillance System already flags changes near leases. However, an RTI response found that states confirmed only 14% of its alerts as illegal mining. Alerts that come without evidence or ranking get ignored.

The Change Sentinel is a pipeline that runs on a laptop using free Sentinel-2 imagery:

- **Clouds and seasons:** it compares full 12-month windows, so cloud cover and seasonal change cancel out.
- **Detection:** it flags ground that has become bare rock or an open pit in nearly every clear view.
- **Case files:** each site gets a case file with a before-and-after image pair, the area with an uncertainty range, a confidence score, the date window, the village, block, tehsil and district, and plain-language reasons for its rank.

Cases are ranked so the top of the list is worth an officer's Monday morning.

## Uploads

| Field | File |
|---|---|
| Prototype (pdf/pptx, max 25 MB) | `submission/ChangeSentinel_Deck.pdf` |
| Code (zip, max 50 MB) | `submission/ChangeSentinel_Source.zip` |
| Video (mp4, max 25 MB) | `submission/ChangeSentinel_Demo.mp4` |

## Repository public URL

https://github.com/YOUR-USERNAME/change-sentinel

## Instructions

No accounts or API keys are needed. You need Python 3.10 or newer (tested on 3.12) and an internet connection.

**See the results without installing anything:** open `output/nuh-subset/index.html` in a browser. It shows the ranked cases from our test run. Click any case to see its case file.

**Run it yourself:**

1. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. Run the test area (about 211 km² of Nuh): `.venv/bin/python -m sentinel config/nuh.yaml --subset 76.86,27.70,77.00,27.86 --top 8`
   - The first run streams about 0.5 GB of imagery: 2–20 minutes, depending on your connection.
   - Re-runs reuse the cached composites.
3. Open `output/nuh-subset/index.html`.

**Whole district:** `.venv/bin/python -m sentinel config/nuh.yaml`. This downloads about 6 GB. On a slow connection, run it on Google Colab or GitHub Codespaces.

**Tests:** `.venv/bin/pip install pytest && .venv/bin/python -m pytest tests` (4 offline tests).

**Another district or change class:** copy `config/nuh.yaml` and edit it. `README.md` explains how.

**Please note:** cases are leads, not proof. The confidence score uses hand-set weights and is not yet calibrated against labelled sites.
