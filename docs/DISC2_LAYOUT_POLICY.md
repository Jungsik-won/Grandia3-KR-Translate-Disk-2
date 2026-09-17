# Disc 2 layout-preservation policy

Disc 2 builds treat the CLEAN Disc 2 image as the layout authority. Korean
payloads may differ in byte length, but a translation must not move executable
scenario structure merely because a generic variable-length rebuild succeeds.

## Required order of preference

1. Keep the original ISO9660 extent and sector allocation when the replacement
   fits. Update only the directory/UDF file size and payload bytes.
2. For scenario records that contain callbacks, branches, timing commands, or
   internal member tables, keep the CLEAN record size, member boundaries, and
   every message's original storage span.
3. Keep inline control bytes at their original message-relative offsets. Shorten
   Korean prose and pad unused bytes instead of moving a control command.
4. Relocate a file only when it cannot fit its original allocation and has been
   shown not to depend on absolute sectors. Record every relocation in the ISO
   build report.
5. Preserve CLEAN Disc 2 files byte-for-byte when no verified Korean candidate
   exists. Disc 1 payloads are not a layout authority for Disc 2.

## Static gates for layout-sensitive scenario files

A candidate is eligible only when all of the following pass:

- candidate MDT size equals the CLEAN MDT size;
- target record size and every internal member boundary equal CLEAN;
- all changes are confined to the allowlisted message storage spans;
- no internal reference relocation is emitted;
- inline control bytes retain their CLEAN relative offsets;
- compressed MDZ fits the original ISO sector allocation whenever possible;
- reverse extraction from the built ISO matches the candidate byte-for-byte;
- the ISO9660 and UDF views agree on extent and size.

`DATA/00450200.MDZ` is the first Disc 2-specific application of this policy.
Its `0x00740000` record must remain 14,976 bytes, its scenario chunk must remain
15,104 bytes, and the file must remain at extent 1,724,366.

## Runtime gate

Identify the active record against every duplicate container before attributing
a mismatch to savestate reuse. Compare the complete record, including compiler
metadata in its header. A matching compressed resource in RAM proves that file
was read, but does not prove its scenario record is active. Slot 6 demonstrated
this: the new `00450200.MDZ` was cached while the active record exactly matched
the untouched `01160901.MDZ`. Header differences previously described as runtime
mutations were actually differences between the source containers.

The meal record exists in `DATA/00450200.MDZ`, `DATA/01160901.MDZ`, and
`DATA/10450201.MDZ`. Apply fixed-span Korean to all three, preserving each
container's own CLEAN header and existing non-scenario Korean chunks. See
`docs/DISC2_DINING_SLOT6_FIX.md` for the evidence and reproducible repair.

Test from a cold boot or a memory-card save before the target area loads. An
emulator savestate contains the already-loaded old MDZ/MDT data, so loading that
state directly can hide a correct disc fix. If a savestate is used for routing,
leave and re-enter the area so the resource is loaded again from the new ISO.
