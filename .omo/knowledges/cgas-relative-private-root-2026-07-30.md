# CGAS relative private root

`scripts/phase3/cgas_characterization_cli.py` resolves a relative
`--private-root` against the resolved `--repository-root` before passing it to
`TrustedStateDirectory.private_path()`. Valid private roots must stay beneath
`tmp/.cgas-characterization`, have no `..` components, preserve NFC spelling,
and contain no existing symlink component. This preserves the documented
relative form `tmp/.cgas-characterization/private` while retaining support for
valid absolute paths.

The subprocess integration test creates an isolated repository under the
workspace `tmp` directory and invokes the documented module command from that
repository with `--repository-root .`.
