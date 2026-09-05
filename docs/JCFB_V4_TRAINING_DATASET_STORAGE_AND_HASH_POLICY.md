# JCFB V4 Training Dataset Storage and Substantive Hash Policy

Policy identity: `v4-training-dataset-storage-policy@1.0.0`
Approved root: `F:\Projects\jcfb-v4\approved_data\training_datasets\`
Staging root: `F:\Projects\jcfb-v4\.runtime\training_dataset_staging\`

Formal dataset artifacts, manifests, lineage manifests, revisions, and
evidence belong only under the approved F-drive root. Build staging is
separate and disposable. C-drive paths, `tests/fixtures`, `src/data`, and
runtime training-dataset paths are forbidden formal targets.

Correction is append-only: create a new artifact and hash, point `supersedes`
to the predecessor, and retain the old version. Overwrite is forbidden.

The substantive hash boundary includes archive snapshot identity/hash, cutoff
profile, builder identity/hash, dataset schema identity/hash, replay policy
identity/hash, generator/config/mapping identities, sample membership, feature
references/hashes, eligibility, and label references/hashes. Execution times,
logging metadata, host-specific absolute paths, host name, process ID, and
duration are volatile and excluded.

The current archive has zero matches. Therefore
`usable_training_sample_count = NOT_COMPUTED` remains unchanged until a
Dataset Builder is actually authorized and executed. Synthetic contract tests
are never formal training artifacts.
