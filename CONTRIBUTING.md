# Contributing

Bug reports, requests and pull requests are welcome.

## Issues

Use the issue forms. For a bug, include the host and version, your OS, the site (address or coordinates) and `log.txt` from the result folder.

## Development

- Code lives in `scripts/`. File prefixes tell where it runs: `cmd_*` host entry points, no prefix = logic modules, `blender_*`, `sketchup_*`, `archicad_*`, `dev_*` = developer tools. Start with [docs/code_map.md](docs/code_map.md) (Korean).
- Tests run without Rhino:

  ```sh
  python3 -m unittest discover tests
  ```

- Build packages locally (nothing is published): `python3 scripts/dev_deploy.py yak|sketchup|blender`.
- User-facing text goes through `tr("Korean source")`. Add the en, es, ja and zh translations to `scripts/i18n.json` in the same change (`tests/test_i18n.py` checks this).
- Keep changes small and focused. Describe what you checked in the pull request.

## License

By contributing, you agree that your contribution is licensed under [GPL-3.0-or-later](LICENSE).
