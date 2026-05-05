# ADR 006 — Lambda packaging via `archive_file` dynamic source blocks

## Status
Accepted

## Context
The first version of the Lambda Terraform module used a
`null_resource` with a `local-exec` `bash` provisioner to stage each
function's source plus the shared package into a build directory:

```hcl
resource "null_resource" "stage" {
  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      rm -rf "${local.build_dir}"
      mkdir -p "${local.build_dir}/shared"
      cp -R "${var.source_dir}/." "${local.build_dir}/"
      cp -R "${var.shared_dir}/." "${local.build_dir}/shared/"
    EOT
  }
}

data "archive_file" "package" {
  type       = "zip"
  source_dir = local.build_dir
  depends_on = [null_resource.stage]
}
```

This worked locally because `terraform apply` had previously created
`.build/` directories that persisted across runs. It **failed on a
fresh GitHub Actions runner** during `terraform plan`, because the
`.build/` directory didn't exist on a clean checkout and `archive_file`
errored when its `source_dir` pointed at a nonexistent path.

## Decision
Replace the staging-directory pattern with `archive_file`'s
`dynamic "source"` blocks, reading each `.py` file directly via
`file()`:

```hcl
data "archive_file" "package" {
  type        = "zip"
  output_path = "${path.module}/.build/${var.function_name}.zip"

  dynamic "source" {
    for_each = fileset(var.source_dir, "**/*.py")
    content {
      content  = file("${var.source_dir}/${source.value}")
      filename = source.value
    }
  }

  dynamic "source" {
    for_each = fileset(var.shared_dir, "**/*.py")
    content {
      content  = file("${var.shared_dir}/${source.value}")
      filename = "shared/${source.value}"
    }
  }
}
```

No `null_resource`, no provisioner, no staging directory. The zip is
built entirely by Terraform from inputs that are present in any clean
checkout.

## Consequences

### Positive
- Works identically on a developer machine, a CI runner, and a
  Terraform Cloud agent. The configuration depends only on files
  that are checked into git.
- Plan-time evaluation reflects actual file contents. If a Python
  file changes, `archive_file` recomputes the hash, `source_code_hash`
  changes, the Lambda updates. No "stale cached zip" failure modes.
- One fewer provider to depend on (`null` was previously in
  `required_providers`, now removed).
- Faster — no shell process spawning per Lambda function.

### Negative
- Only `.py` files are vendored. Anything else (data files, configs,
  binary deps) would need to be added explicitly. At present the
  Lambdas are pure Python with stdlib + boto3-from-runtime, so this
  isn't a constraint.
- The `dynamic "source"` block is more verbose than `source_dir`. A
  reader has to grok the doubled block to understand the layout.

### How this was caught
The bug was invisible to local development because `.build/` directories
persisted from prior applies. CI is the **only** environment that
reliably starts from a clean checkout. This is the canonical example
of why CI/CD matters: it surfaces hidden assumptions that "work on my
machine" hides.
