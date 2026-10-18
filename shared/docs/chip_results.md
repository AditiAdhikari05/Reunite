# LinuxONE AI accelerator results

Test: chip_bench.py (4-layer neural network, 8,192 pairs per batch, 20 repeats)
Same model and data both times. Only difference: accelerator on or off.

| Setting | Pairs scored per second | Total time |
|---|---|---|
| Accelerator OFF (NNPA_DEVICES=0) | 41,918 | 3.91 s |
| Accelerator ON (default) | 237,224 | 0.69 s |

Speedup: about 5.7x.
Scores differ by about 0.0005 between runs (the accelerator uses lower precision internally).

Evidence: with ZDNN_ENABLE_PRECHECK=true, TF_CPP_MIN_LOG_LEVEL=0 and TF_CPP_VMODULE='remapper=1',
the log shows "ZRemapper remapping to Z op" for 3 layers and a ZStickify node.
Screenshot: docs/chip_proof.png (upload it here).

Environment: LinuxONE community cloud VM, 3 virtual CPUs, 8 GB RAM, z/VM 7.3.0,
lscpu machine type 9175, CPU flags include nnpa and vxe2,
TensorFlow 2.18.1 with ibm-zdnn-plugin 2.3.0, libzdnn.so.0 loaded.

Caveats: small model with random weights, one test. Rerun with the real match scorer and update this file.

Reproduce:
  NNPA_DEVICES=0 python chip_bench.py
  python chip_bench.py
