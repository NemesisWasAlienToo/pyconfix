# Aliases

Reusable enums and tasks, kept in their own file.

```sh
pyconfix --run GREET
pyconfix --run GOODBYE
```

```text
Hello
Goodbye
```

* `aliases.yaml` defines the aliases
* `pyconfixfile.yaml` includes it first, then uses them
* `text` is an argument, with `Hello` as its default
