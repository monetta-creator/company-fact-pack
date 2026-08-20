"""Pre-download embedding + reranker models as an explicit checkpoint step."""

from factpack import embed
from factpack.runlog import run_isolated


def main() -> None:
    def run(log) -> None:
        v = embed.embed_passages(["warmup"])
        log.note(f"embedder ready, dim={v.shape[1]}")
        s = embed.rerank("warmup", ["warmup passage"])
        log.note(f"reranker ready, score={float(s[0]):.3f}")

    run_isolated("compile.warm_models", run)


if __name__ == "__main__":
    main()
