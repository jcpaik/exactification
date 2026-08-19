# Blind input: Grzesik pentagon SDP

This folder contains only the exact SDP model, the SDPA-GMP discovery input and
output, and a language-neutral transcription of the numerical optimizer. It
does not contain Grzesik's published rational Gram matrices.

The fixed objective is `24/625`. The task is to construct any exact rational
certificate attaining that value; matching the paper's particular optimizer is
neither required nor expected.

Coordinates in `model.json` are zero-based. Each off-diagonal term multiplies
the displayed symmetric matrix entry once, as specified by
`exact-block-sdp-model-v1`.

