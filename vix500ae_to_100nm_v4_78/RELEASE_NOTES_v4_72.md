# v4.72

Focused motion proof update after v4.71 evidence.

Changes:
- Keeps Pico firmware v2.7 with X5 debounce.
- Uses Candidate B only: GF0 GI0.5 GP2 GV1 FT0, CL=2%.
- Waits longer after applying gains before scoring.
- Scores the quiet tail of the hold window, not the whole post-gain pull-in transient.
- Proceeds to sham and 500/200/100 nm ladder only if the tail is quiet.
- Auto-zips evidence as before.
