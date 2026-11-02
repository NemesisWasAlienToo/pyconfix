# Tasks

Shell tasks that run other tasks.

```sh
pyconfix --run DEPLOY -o RELEASE=true
```

```text
Building...
Build done
Testing...
Deploying...
```

Without `RELEASE=true`, `DEPLOY` is disabled and exits with 1.

* `deps` decides if a task is available
* `needs` runs other tasks first
