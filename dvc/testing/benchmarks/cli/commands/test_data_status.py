from shutil import rmtree


def test_data_status(bench_dvc, tmp_dir, scm, dvc, make_dataset):
    args = ("data", "status")
    dataset = make_dataset(cache=True, files=True, dvcfile=True, commit=False)
    scm.ignore(dataset)
    rmtree(dvc.tmp_dir)

    bench_dvc(*args, name="new")
    bench_dvc(*args, name="noop")

    tmp_dir.scm_add(
        [dataset.with_suffix(".dvc").name, ".gitignore"], commit="add dataset"
    )

    (dataset / "new").write_text("new")
    bench_dvc(*args, name="changed")
    bench_dvc(*args, name="changed-noop")


def test_data_status_all_flags(bench_dvc, tmp_dir, scm, dvc, make_dataset):
    args = (
        "data",
        "status",
        "--granular",
        "--unchanged",
        "--untracked-files",
        "--json",
    )
    dataset = make_dataset(cache=True, files=True, dvcfile=True, commit=False)
    scm.ignore(dataset)
    rmtree(dvc.tmp_dir)

    bench_dvc(*args, name="new")
    bench_dvc(*args, name="noop")

    tmp_dir.scm_add(
        [dataset.with_suffix(".dvc").name, ".gitignore"], commit="add dataset"
    )

    (dataset / "new").write_text("new")
    bench_dvc(*args, name="changed")
    bench_dvc(*args, name="changed-noop")
