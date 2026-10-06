# SSAMS local biometric components: model card and license inventory

**Read this before enabling enrollment.** SSAMS processes facial imagery and treats the resulting face representation as sensitive biometric information. This document is a technical inventory, not legal advice, a privacy-impact assessment, evidence of demographic fairness, or permission to deploy. The institution must review applicable law, model terms, training-data provenance, accessibility accommodations, consent, retention, and appeal procedures before use.

## Intended use and decision flow

- OpenCV YuNet detects the single visible face in a captured frame. OpenCV SFace produces a numerical representation and performs a **one-to-one comparison** with the authenticated student's own enrolled template; SSAMS does not search a gallery of identities.
- A separate MediaPipe Face Mesh process analyzes temporal eye-aspect and head-pose measurements for a randomized blink/head-turn/neutral challenge. It is a basic active liveness signal, not a certified presentation-attack detector.
- Attendance is written only after the server checks the authenticated user, active enrollment, class/session window, geofence, challenge ownership/expiry/completion, model checks, template decryption, and face-similarity threshold. These checks reduce risk but do not guarantee identity, presence, fairness, or spoof resistance.
- The default SFace cosine-similarity threshold is `0.363`. It is a starting configuration value, not a locally validated operating point or an accuracy guarantee. Before deployment, test false accepts/rejects on representative consented data, document thresholds and uncertainty, and provide a non-biometric alternative and human appeal process.
- No model or raw camera frame is downloaded, logged, or persisted automatically at runtime. Frame data is processed in memory by the API; the encrypted embedding, consent metadata, verification outcome, and limited challenge/geofence metadata are persisted according to the application retention design. Verify the implementation and backups in your own release.

## Exact model files

| Component | File | Publisher/source revision | SHA-256 | Published license note |
|---|---|---|---|---|
| Face detector | `face_detection_yunet_2023mar.onnx` | OpenCV Zoo, revision [`47534e27c9851bb1128ccc0102f1145e27f23f98`](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet) | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | YuNet model directory says MIT; its license identifies copyright © 2020 Shiqi Yu. Keep the model-directory notice with any permitted redistributed copy. |
| Face embedding | `face_recognition_sface_2021dec.onnx` | OpenCV Zoo, revision [`ba91a3b91d00d76e86540d4013f944bd6b514e39`](https://github.com/opencv/opencv_zoo/tree/ba91a3b91d00d76e86540d4013f944bd6b514e39/models/face_recognition_sface) | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | OpenCV Zoo SFace model directory provides Apache License 2.0. Upstream issue discussion leaves training-data lineage/authorization and downstream-use questions unresolved; do not infer that a code/weights license resolves dataset rights. |
| Temporal landmarks | MediaPipe `solutions.face_mesh.FaceMesh` supplied by `mediapipe==0.10.21` | Pinned Python dependency; package initializes its bundled local Face Mesh assets, with no download initiated by SSAMS | Package wheel provides the model/runtime; no standalone model file is committed or downloaded by this project | MediaPipe source and Face Mesh V2 model card are Apache-2.0. The legacy `solutions.face_mesh` assets in the pinned wheel may not be identical to the V2 Tasks model card; check wheel notices/model documentation and training-data provenance for the exact installed assets before institutional approval. |

**Upstream references:** [YuNet model README and license](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet), [SFace model directory and license](https://github.com/opencv/opencv_zoo/tree/ba91a3b91d00d76e86540d4013f944bd6b514e39/models/face_recognition_sface), [SFace provenance/commercial-use discussion](https://github.com/opencv/opencv_zoo/issues/313), [MediaPipe Face Mesh V2 model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf), [OpenCV Zoo policy on per-model licenses](https://github.com/opencv/opencv_zoo#license).

`models/SHA256SUMS` contains the two expected model digests. The SFace issue is a signal to obtain a current written legal review, not a statement that a use is or is not licensed. Institutions must make their own determination before commercial or high-impact use.

## Download and offline install

Weights are intentionally absent from version control. The backend CLI downloads each exact file from immutable GitHub revisions, checks the complete SHA-256, refuses to replace a mismatched existing file, and never downloads models during app startup:

```bash
cd backend
.venv/bin/python -m app.cli install-models --accept-model-terms
.venv/bin/python -m app.cli model-check
```

The equivalent PowerShell commands are:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m app.cli install-models --accept-model-terms
.\.venv\Scripts\python.exe -m app.cli model-check
```

For an air-gapped host, download the files on an approved machine using the exact revision URLs above, verify the two digests in `SHA256SUMS`, transfer them through the institution's controlled process into the configured `MODEL_DIR`, and run `model-check` on the target host. Do not copy an unchecked model or disable checksum validation. After successful installation, inference is local CPU execution and requires no network.

## Limitations and required local evaluation

- YuNet and SFace are pretrained general-purpose components, not independently validated SSAMS attendance tools. Pose, blur, lighting, sensor quality, compression, masks, demographic factors, disability, and the enrollment process can influence errors.
- SFace produces a similarity score, not a calibrated probability. A hard threshold can yield false matches and false rejections; one global threshold is not proof of equal performance.
- The MediaPipe checks use facial landmarks, simple eye ratios, head-pose estimates, timing, frame hashes, and randomized prompts. They do not reliably stop replay, injected video, deepfakes, masks, coercion, or sophisticated presentation attacks. Challenge success is not proof of liveness.
- Browser geolocation is an untrusted sensor. Accuracy, spoofing, device permissions, indoor multipath, and campus boundaries require operational controls and an appeal path.
- Test locally on supported hardware and representative, consented images with independent review; document limitations, sample size, subgroup results, thresholds, failure handling, retention, and alternatives. Do not infer performance from the mere fact that the model loads.
- Avoid collecting unnecessary biometric samples. The application uses separate enrollment and live-compare steps; changing the model or threshold should require a compatibility/reenrollment plan and explicit review.

## Licensing and notices

The application code license is in the repository root `LICENSE`. The two ONNX weights are downloaded from separately licensed upstream model directories; they are not embedded in the application source. Retain the corresponding upstream license and attribution when lawfully redistributing model files. The MediaPipe wheel has its own third-party notices and bundled assets; retain and review them for the exact version. No claim is made about model training-data consent, dataset license compatibility, or legal clearance for any particular institution or jurisdiction.
