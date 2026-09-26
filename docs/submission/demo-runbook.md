# Live demo runbook (draft 1)

For a 5–7 minute live walkthrough (a call with the organisers, a judging session, or a recording take). Two modes: **live GPT-6** (the real thing, ~4–10 minutes of model time) and **Demo mode** (scripted, a minute, no key) as the fallback. Practise both.

## Setup (before anyone is watching)

1. `kin serve` from the repo folder; the banner prints the LAN URL for the phone.
2. Settings → provider OpenAI → key verified (green pill "OpenAI · gpt-6-astra"). Keep a second browser tab on a finished demo session (the bottle handle, exported) in case the live run misbehaves.
3. Calibration sheet on the table, the bottle, the snapped handle, the printed handle and coupon within reach.
4. Phone on the same Wi-Fi with the app open on the home page.

## The walk (live)

| min | do | say |
|---|---|---|
| 0:00 | Hold up the snapped handle and the printed one. | "Same bottle. This one came from three photos." |
| 0:30 | Phone: *Photograph what broke* → three photos (object, break, neck) → one sentence → *Analyze*. | "It identifies the part and — this is the important bit — the features it has to mate with." |
| 1:30 | Desktop: the session opens on **Round 1**. Read the requests out loud. Take the neck-on-sheet photo with the phone into the slot. Watch "measured: 43.1 mm" appear. Type the ring height. *Check what's still missing* → ready. | "It asks for the photo that resolves each unknown and measures it on the sheet. When it knows enough, it stops asking." |
| 2:30 | Evidence tab (10 s). | "Every number knows where it came from." |
| 2:45 | *Design this part* (Standard). While it runs: Graph tab → the pipeline lighting up; back to the guide's progress card. | "The model writes OpenSCAD; we compile it and measure the mesh. The drawing you'll see is generated from the mesh — the model can't fake it." |
| 4:00 | First iteration lands: Sections tab, point at a dimension line (red or green). If red: the timeline shows the designer's next change. | "That's the ring bore. It has to be 43.25 with clearance; the checker read 43.45 off the mesh." |
| 5:00 | Critic card. If it says pass, open `eval/reports/critic_probe/README.md` and show `hole_in_bridge` (10 s). | "A second model with no access to the code reviews the drawings. Here it caught a hole through the load path." |
| 5:45 | Review → Export. Coupon popover, the printed coupon on the neck. Print step: the files, the print card. | "Coupon first, then the part. Every dimension is a slider in the exported file." |
| 6:30 | Close with the printed handle on the bottle. | "Photograph what broke. Print what fits." |

## Fallbacks

- Model slow/unavailable → say so, switch the browser tab to the finished session; the story is identical from the Review step on.
- Photo measurement finds nothing (glare, tilt) → the card shows the grader's instruction; retake with the sheet flat and the phone straight above; or type the ruler reading — the flow continues either way.
- Compile error in iteration 1 → it is expected sometimes; the timeline shows the fix. Never restart the run on stage.
- Demo mode (Settings → Demo mode) runs the whole thing scripted in ~60 s; say it is scripted.

## Things not to say

- Don't promise sub-0.1 mm on real photos; say "within half a millimetre on synthetic ground truth; the coupon confirms the fit".
- Don't call the critic "always right"; quote the probe (4/5, missed the fillets).
- Don't quote the A/B numbers until they are re-run on GPT-6.
