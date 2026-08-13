# v4.65 — fixed post-enable settle sampling

- Fixes the v4.64 post-enable settle probe false confidence mode where optional ViX PT/PF/ST2 reads could consume the whole window and leave only one sample.
- Repeated no-motion windows now avoid optional R(PT) reads, require a minimum sample count, and refuse pass/fail classification from insufficient samples.
- Keeps the same no-commanded-motion intent: enable once, allow bounded transient, then measure whether already-energised hold becomes quiet.
