# Synapse resolver fixtures — Feature 1 (cross-file callee resolution).
# Marks this directory as a Python package so the relative imports inside
# the fixture modules (`from .b import baz`) parse cleanly at static-analysis
# time. These files are NOT meant to be imported by tests; tests COPY them
# into a tmp_path project root and run the resolver over the copy.
