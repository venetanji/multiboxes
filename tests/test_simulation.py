import math

import pytest

from multibox.simulation import Config, Input, World


def advance(world, seconds, *, now=0):
    for i in range(round(seconds * world.config.physics_hz)):
        world.step(now + i / world.config.physics_hz)


def put(world, player, x, y, vy=0):
    player.body.position = x, y
    player.body.velocity = 0, vy
    player.body.angle = 0
    world.space.reindex_shapes_for_body(player.body)


def land(world, player):
    put(world, player, 400, world.config.height - world.config.player_size / 2 - 2)
    advance(world, 0.3)
    assert player.jump_ready


def test_balanced_teams_unique_nonoverlapping_spawns_and_cleanup():
    world = World()
    players = [world.add_player(f"student {i}", now=0) for i in range(150)]
    assert [p.team for p in players].count(1) == 75
    assert [p.team for p in players].count(2) == 75
    for i, a in enumerate(players):
        for b in players[i + 1:]:
            assert a.body.position.get_distance(b.body.position) >= world.config.player_size
    removed = players[0]
    world.remove_player(removed.id)
    world.remove_player(removed.id)  # Idempotent cleanup.
    assert removed.body not in world.space.bodies
    assert removed.shape not in world.space.shapes
    assert world.add_player("replacement", now=0).team == removed.team
    assert len(world.space.bodies) == 150


def test_capacity_and_config_are_bounded():
    world = World(Config(max_players=2))
    world.add_player("a", now=0)
    world.add_player("b", now=0)
    with pytest.raises(ValueError, match="full"):
        world.add_player("c", now=0)
    for config in [{"max_players": 1000}, {"cell_size": 1}, {"round_seconds": 0}, {"physics_hz": 0}]:
        with pytest.raises(ValueError):
            Config(**config)


def test_input_frequency_does_not_change_force_and_down_descends_faster():
    a, b = World(), World()
    pa, pb = a.add_player("a", now=0), b.add_player("b", now=0)
    for world, player in [(a, pa), (b, pb)]:
        put(world, player, 400, 100)
    a.set_input(pa.id, Input(right=True), now=0)
    for _ in range(20):
        b.set_input(pb.id, Input(right=True), now=0)
    advance(a, 0.2)
    advance(b, 0.2)
    assert pa.body.position == pb.body.position
    assert pa.body.velocity == pb.body.velocity
    b.set_input(pb.id, Input(down=True), now=0.2)
    advance(a, 0.2, now=0.2)
    advance(b, 0.2, now=0.2)
    assert pb.body.velocity.y > pa.body.velocity.y


def test_jump_is_one_impulse_requires_release_and_new_landing():
    world = World()
    player = world.add_player("jumper", now=0)
    land(world, player)
    world.set_input(player.id, Input(jump=True), now=0.3)
    world.step(0.3)
    assert player.body.velocity.y < -300
    assert not player.jump_ready
    # Releasing/repressing immediately must not reuse the old contact arbiter.
    world.set_input(player.id, Input(), now=0.31)
    world.set_input(player.id, Input(jump=True), now=0.31)
    before = player.body.velocity.y
    world.step(0.32)
    assert player.body.velocity.y > before
    # Hold through a complete flight/landing, with heartbeats, then no auto-jump.
    for i in range(100):
        t = 0.34 + i / 60
        world.set_input(player.id, Input(jump=True), now=t)
        world.step(t)
    assert player.jump_ready
    assert abs(player.body.velocity.y) < 2
    world.set_input(player.id, Input(), now=2.1)
    world.set_input(player.id, Input(jump=True), now=2.1)
    world.step(2.1)
    assert player.body.velocity.y < -300
    assert world.jumps == 2


def test_airborne_or_side_contact_does_not_recharge_jump():
    world = World()
    player = world.add_player("side", now=0)
    put(world, player, 11.9, 200)
    advance(world, 0.1)
    assert not player.jump_ready
    for i in range(8):
        world.set_input(player.id, Input(), now=i / 100)
        world.set_input(player.id, Input(jump=True), now=i / 100)
        world.step(i / 100)
    assert player.body.velocity.y > 0
    assert world.jumps == 0


def test_support_from_another_player_recharges():
    world = World()
    lower = world.add_player("lower", now=0)
    upper = world.add_player("upper", now=0)
    size = world.config.player_size
    put(world, lower, 400, world.config.height - size / 2 - 1)
    put(world, upper, 400, world.config.height - size * 1.5 - 2)
    advance(world, 0.6)
    assert upper.jump_ready
    world.set_input(upper.id, Input(jump=True), now=0.6)
    world.step(0.6)
    assert upper.body.velocity.y < -300


def test_ascending_never_paints_descending_paints_and_scores_match_grid():
    world = World()
    player = world.add_player("painter", now=0)
    put(world, player, 400, 200, vy=-100)
    world.step(0)
    assert world.counts == [len(world.paint), 0, 0]
    player.body.velocity = 0, 100
    world.step(0.1)
    assert world.counts[player.team] > 0
    assert world.counts == [world.paint.count(ord(str(i))) for i in range(3)]
    state = world.snapshot()
    assert sum(state["coverage"]) == pytest.approx(100, abs=0.11)
    assert len(state["paint"]) == world.config.width // 24 * (world.config.height // 24)


def test_same_tick_paint_is_deterministic_and_last_valid_paint_wins():
    def run():
        world = World()
        a, b = world.add_player("a", now=0), world.add_player("b", now=0)
        # Overlapping paint footprints, but bodies separated vertically.
        put(world, a, 402, 201, 50)
        put(world, b, 426, 201, 50)
        world.step(0)
        return world.snapshot()["paint"], world.counts
    assert run() == run()
    world = World()
    a, b = world.add_player("a", now=0), world.add_player("b", now=0)
    put(world, a, 400, 200, 50)
    put(world, b, 900, 200, -100)
    world.step(0)
    first = world.counts[1]
    put(world, a, 100, 100, -100)
    put(world, b, 400, 201, 50)
    world.step(0.1)
    assert world.counts[1] < first
    assert world.counts[2] > 0


def test_stale_input_clears_all_held_and_pending_jump():
    world = World()
    player = world.add_player("stale", now=0)
    world.set_input(player.id, Input(right=True, down=True, jump=True), now=0)
    world.step(1)
    assert player.input == Input()
    assert not player.pending_jump
    assert player.body.velocity.x == 0


def test_round_end_freezes_paint_and_teacher_reset_is_complete():
    world = World(Config(round_seconds=1, intermission_seconds=0.5))
    player = world.add_player("round", now=0)
    advance(world, 1.1)
    assert world.phase == "finished"
    paint = bytes(world.paint)
    advance(world, 0.2)
    assert world.paint == paint
    world.reset_round(start=False)
    assert world.phase == "waiting"
    assert world.counts == [len(world.paint), 0, 0]
    assert player.input == Input()
    world.reset_round(start=True)
    assert world.phase == "playing"
    assert math.isclose(world.remaining, 1)
    assert world.snapshot()["round"] == 3
