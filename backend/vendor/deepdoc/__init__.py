#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#  Licensed under the Apache License, Version 2.0.
#
# Patched in this repo: removed `beartype.claw.beartype_this_package()` —
# upstream uses beartype for runtime type-checking instrumentation, which
# isn't needed for benchmark use and would add a runtime dependency. See
# `vendor/VENDORED_FROM.md`.
