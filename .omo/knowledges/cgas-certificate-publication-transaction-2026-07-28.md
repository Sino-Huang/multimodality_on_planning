# CGAS Certificate Publication Transaction

- Certificate publication owns only `steps/`, `schema/`, and
  `steps_manifest.json`; do not replace the output root because it can contain
  independently owned `source/` and `alignment/` directories.
- A candidate is complete before publication. For an update, move each old
  artifact into one private transaction backup, install its candidate, and keep
  every backup until all three artifacts have installed.
- On an `os.replace()` failure, reverse installed entries first, restore each
  backup to its contract path, remove transaction residue, and re-raise the
  primary error. The caller removes the restored candidate directory.
- Regression coverage must fault all three first-publish candidate replacements
  and all six update backup/candidate replacements. Assert exact byte-tree
  equality and no `.<output>.steps-*` or `.<output>.publication-*` paths.
