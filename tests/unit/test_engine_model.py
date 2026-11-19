from risksched.serving.engine_model import EngineModel, EngineParams


def drain(eng, limit=100000):
    evs, t = [], 0.0
    for _ in range(limit):
        if not eng.has_work():
            break
        dt, e = eng.step()
        assert dt > 0
        t += dt
        evs.extend(e)
    return evs, t


def test_single_request_exact_tokens():
    eng = EngineModel(EngineParams())
    assert eng.add_request("r", 100, 50, target_out=20) is None
    evs, _ = drain(eng)
    kinds = [e.kind for e in evs]
    assert kinds[0] == "first_token" and kinds[-1] == "finished"
    assert evs[-1].generated == 20
    assert kinds.count("token") == 19
    assert eng.free_blocks == eng.params.kv_blocks_total


def test_target_capped_by_max_tokens():
    eng = EngineModel(EngineParams())
    eng.add_request("r", 10, 5, target_out=999)
    evs, _ = drain(eng)
    assert evs[-1].generated == 5


def test_rejects_over_context_and_capacity():
    eng = EngineModel(EngineParams(max_model_len=100))
    assert eng.add_request("r", 90, 20, 5).kind == "rejected"
    eng2 = EngineModel(EngineParams(kv_blocks_total=4, block_size=16, max_model_len=1000))
    assert eng2.add_request("r", 60, 10, 5).kind == "rejected"


def test_kv_pressure_preempts_but_everything_finishes():
    p = EngineParams(kv_blocks_total=64, block_size=16, max_num_seqs=16, max_model_len=1024)
    eng = EngineModel(p)
    for i in range(12):
        assert eng.add_request(f"r{i}", 200, 300, target_out=300) is None
    evs, _ = drain(eng)
    finished = [e for e in evs if e.kind == "finished"]
    assert len(finished) == 12
    assert all(e.generated == 300 for e in finished)
    assert eng.stats.num_preemptions_total > 0
    assert eng.free_blocks == p.kv_blocks_total
    # every request emits first_token exactly once even across preemption
    assert sum(e.kind == "first_token" for e in evs) == 12


def test_chunked_prefill_long_prompt():
    eng = EngineModel(EngineParams(max_num_batched_tokens=512))
    eng.add_request("r", 3000, 4, 4)
    evs, _ = drain(eng)
    assert eng.stats.steps_total >= 3000 // 512
    assert evs[-1].kind == "finished"


def test_deterministic():
    def run():
        eng = EngineModel(EngineParams(kv_blocks_total=128))
        for i in range(20):
            eng.add_request(f"r{i}", 100 + i * 10, 200, 50 + i)
        evs, t = drain(eng)
        return [(e.rid, e.kind, e.generated) for e in evs], t
    assert run() == run()


def test_abort_frees_blocks():
    eng = EngineModel(EngineParams())
    eng.add_request("r", 500, 100, 100)
    eng.step()
    assert eng.free_blocks < eng.params.kv_blocks_total
    assert eng.abort("r")
    assert eng.free_blocks == eng.params.kv_blocks_total
    assert not eng.abort("r")
