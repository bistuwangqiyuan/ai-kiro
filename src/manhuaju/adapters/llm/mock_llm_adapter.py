"""Mock LLM adapter — deterministic templated structured output.

Each agent has a request-type ``op`` that selects the templating function. All
outputs are pure functions of the request payload (so determinism KPI holds).
We do not import any agent code here to avoid cycles.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from manhuaju.utils.canonical_json import sha256_of


def _seeded(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()[:8], "big")


def _stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}_{_seeded(*parts) % 10**8:08d}"


def _split_acts(novel_text: str) -> list[str]:
    """Naively split on triple-newline / chapter markers; we can't trust the
    text to come with explicit acts, so produce 3 roughly equal slices."""
    n = len(novel_text)
    return [novel_text[: n // 3], novel_text[n // 3 : 2 * n // 3], novel_text[2 * n // 3 :]]


_CHAR_NAME_RE = re.compile(r"([\u4e00-\u9fa5]{2,3})(?=[“:：])|([A-Z][a-z]{2,15})")


def _scan_named_entities(text: str, top_k: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for m in _CHAR_NAME_RE.finditer(text):
        name = (m.group(1) or m.group(2) or "").strip()
        if not name or len(name) < 2:
            continue
        counts[name] = counts.get(name, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, _ in ordered[:top_k]]


class MockLLMAdapter:
    name = "MockLLMAdapter"

    # ----------------- StoryArchitect -----------------
    def story_blueprint(self, *, novel_text: str, project_id: str, seed: int) -> dict[str, Any]:
        names = _scan_named_entities(novel_text)
        # If insufficient, supplement with deterministic generic role names
        defaults = ["林云雀", "陈翊", "宋决"]
        while len(names) < 3:
            names.append(defaults[len(names)])
        leads = names[:2]
        supports = names[2:5]

        characters = []
        for i, n in enumerate(leads):
            characters.append(
                {
                    "char_id": _stable_id("char", project_id, n),
                    "canonical_name": n,
                    "aliases": [n[:1] + "氏"] if i == 0 else [],
                    "screen_role": "lead",
                }
            )
        for n in supports:
            characters.append(
                {
                    "char_id": _stable_id("char", project_id, n),
                    "canonical_name": n,
                    "aliases": [],
                    "screen_role": "support",
                }
            )

        locations = [
            {
                "location_id": "loc_skyport",
                "name": "天港",
                "description": "钢蓝色调的高空浮岛。",
                "palette_hex": ["#0a1f3a", "#7393b3", "#cfd9e3", "#e8c267"],
            },
            {
                "location_id": "loc_archive",
                "name": "档案塔",
                "description": "暖橙色的图书馆塔楼。",
                "palette_hex": ["#3a1f0a", "#b3733b", "#e3cfd9", "#67e8c2"],
            },
            {
                "location_id": "loc_underground",
                "name": "地下走廊",
                "description": "冷绿主调的隐秘通道。",
                "palette_hex": ["#0a3a1f", "#3bb373", "#cfe3d9", "#e8c267"],
            },
        ]
        timeline = [
            {
                "event_id": _stable_id("ev", project_id, i),
                "story_time": i,
                "description": f"主线节拍 {i+1}",
                "location_id": locations[i % len(locations)]["location_id"],
                "characters_present": [c["char_id"] for c in characters[: 1 + i % 3]],
            }
            for i in range(6)
        ]
        relations = {
            "nodes": [c["char_id"] for c in characters],
            "edges": [
                {"src": characters[0]["char_id"], "dst": characters[1]["char_id"], "type": "rival"}
            ]
            + (
                [{"src": characters[0]["char_id"], "dst": characters[2]["char_id"], "type": "mentor"}]
                if len(characters) > 2
                else []
            ),
        }
        motifs = [{"motif_id": "motif_skyfall", "description": "天港暮色"}]
        out = {
            "blueprint_id": _stable_id("bp", project_id, seed),
            "world_rules": [
                {"rule_id": "wr_no_real_world_brands", "text": "不出现现实品牌名"},
                {"rule_id": "wr_no_real_persons", "text": "不出现现实政治人物"},
            ],
            "timeline": timeline,
            "locations": locations,
            "characters": characters,
            "relations": relations,
            "motifs": motifs,
            "judge_scores": {"faithfulness": 0.91, "coverage": 0.93, "structure": 0.92},
            "provenance_passages": {
                c["char_id"]: [(0, min(64, len(novel_text)))] for c in characters
            },
        }
        out["blueprint_sha"] = sha256_of(out)
        return out

    # ----------------- EpisodePlanner -----------------
    def episode_plan(self, *, blueprint: dict[str, Any], episode_count: int, seed: int) -> dict[str, Any]:
        # Use deep slice of timeline per episode
        episodes = []
        beats_per_ep = max(3, len(blueprint["timeline"]) // max(1, episode_count))
        for i in range(episode_count):
            ep_id = f"ep{i+1:02d}"
            slice_start = i * beats_per_ep
            slice_end = slice_start + beats_per_ep
            tl = blueprint["timeline"][slice_start:slice_end] or [blueprint["timeline"][-1]]
            characters = sorted({c for ev in tl for c in ev["characters_present"]})
            locations = sorted({ev["location_id"] for ev in tl})
            beats = [
                {
                    "beat_id": _stable_id("beat", ep_id, j),
                    "summary": f"{ep_id}-第{j+1}拍",
                    "seconds": 18 + (j * 5 + i) % 12,
                }
                for j, _ in enumerate(tl)
            ]
            target_seconds = sum(b["seconds"] for b in beats)
            episodes.append(
                {
                    "episode_id": ep_id,
                    "title": f"第{i+1}集",
                    "synopsis_short": f"{ep_id} 的转折与悬念",
                    "synopsis_long": f"{ep_id} 主线：{tl[0]['description']} -> {tl[-1]['description']}",
                    "target_seconds": target_seconds,
                    "beats": beats,
                    "opening": {"seconds": 5, "summary": "倒序开场，留下钩子"},
                    "closing": {"summary": "反转 + 悬念", "cliffhanger_strength": 4},
                    "characters_present": characters,
                    "locations_present": locations,
                }
            )
        out = {
            "plan_id": _stable_id("plan", seed),
            "episodes": episodes,
            "budgets": {
                "per_episode_credits": [120 for _ in range(episode_count)],
                "reserve_credits": 30,
            },
            "judge_scores": {"faithfulness": 0.93, "coverage": 0.92, "structure": 0.94},
        }
        out["plan_sha"] = sha256_of(out)
        return out

    # ----------------- CharacterBible -----------------
    def character_bible(self, *, character_stub: dict[str, Any], blueprint: dict[str, Any], seed: int) -> dict[str, Any]:
        char_id = character_stub["char_id"]
        is_lead = character_stub["screen_role"] == "lead"
        outfits = []
        n_outfits = 5 if is_lead else 3
        for k in range(n_outfits):
            outfits.append(
                {
                    "outfit_id": f"{char_id}_outfit_{k:02d}",
                    "name": ["日常", "战服", "礼装", "便装", "宴会"][k % 5],
                    "palette_hex": [
                        f"#{(0x113355 + (_seeded(char_id, k, p) % 0xAAAAAA)) & 0xFFFFFF:06x}"
                        for p in range(5)
                    ],
                    "fabric": "linen" if k % 2 == 0 else "silk",
                    "silhouette": "long-coat" if k == 0 else ("armor" if k == 1 else "tunic"),
                    "accessories": [],
                }
            )
        nodes = [
            {
                "node_id": f"{char_id}_n{i}",
                "age_band": "young_adult",
                "hair_state": "tidy" if i == 0 else "disheveled",
                "wound_state": "intact" if i < 2 else "scratched",
                "outfit_id": outfits[i % len(outfits)]["outfit_id"],
            }
            for i in range(3)
        ]
        transitions = [
            {
                "from_node": nodes[0]["node_id"],
                "to_node": nodes[1]["node_id"],
                "trigger_beat_id": "ep01_b01",
                "justification": "首次冲突",
            },
            {
                "from_node": nodes[1]["node_id"],
                "to_node": nodes[2]["node_id"],
                "trigger_beat_id": "ep02_b02",
                "justification": "决战受伤",
            },
        ]
        out = {
            "char_id": char_id,
            "canonical_name": character_stub["canonical_name"],
            "aliases": character_stub.get("aliases", []),
            "screen_role": character_stub["screen_role"],
            "appearance": {
                "gender": "female" if is_lead else "male",
                "ethnicity": "unspecified",
                "age_band": "young_adult",
                "height_band": "average",
                "body_type": "slim",
                "eye_color": "amber" if is_lead else "dark-grey",
                "hair_length": "long" if is_lead else "short",
                "hair_color": "auburn" if is_lead else "ink-black",
                "hair_texture": "wavy" if is_lead else "straight",
                "hairstyle": "side-braid" if is_lead else "swept-back",
                "distinguishing_marks": [],
                "essence": f"{character_stub['canonical_name']} 的核心气质：克制、机敏、坚韧。",
                "face_palette_hex": ["#cdb79e", "#3a3a3a"],
            },
            "outfit_library": outfits,
            "voice_profile": {
                "voice_id": f"{char_id}_voice_v1",
                "base_pitch_hz": 220 if is_lead else 180,
                "timbre": "warm" if is_lead else "neutral",
                "energy": "medium",
                "locale": "zh-CN",
            },
            "personality": {
                "summary": "克制、机敏、决断果断。",
                "traits": ["克制", "机敏", "果断"],
            },
            "state_machine": {
                "nodes": nodes,
                "transitions": transitions,
                "initial_node": nodes[0]["node_id"],
            },
            "relations": [],
            "provenance_passages": [(0, 64)],
        }
        out["bible_sha"] = sha256_of(out)
        return out

    # ----------------- StyleLock -----------------
    def style_lock(self, *, project_id: str, blueprint: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        project_palette = sorted(
            {h for loc in blueprint["locations"] for h in loc["palette_hex"]}
        )[:8]
        while len(project_palette) < 8:
            project_palette.append(f"#{((_seeded(project_id, len(project_palette))) % 0xFFFFFF):06x}")
        out = {
            "preset_id": config.get("style_preset_id", "cinematic_2d_v1"),
            "aspect_ratio": config.get("aspect_ratio", "9:16"),
            "resolution": config.get("resolution", "1080p"),
            "fps": int(config.get("fps", 24)),
            "duration_units": [5, 10, 15],
            "project_palette_hex": project_palette,
            "location_palette": {loc["location_id"]: loc["palette_hex"] for loc in blueprint["locations"]},
            "immutable": True,
        }
        out["style_sha"] = sha256_of(out)
        return out

    # ----------------- ScriptWriter -----------------
    def write_script(self, *, episode: dict[str, Any], characters: list[dict[str, Any]], seed: int) -> dict[str, Any]:
        ep_id = episode["episode_id"]
        chars_in_ep = episode["characters_present"]
        char_lookup = {c["char_id"]: c for c in characters}
        scenes = []
        dialogues = []
        cumulative = 0
        for i, beat in enumerate(episode["beats"]):
            scene_id = f"{ep_id}_sc{i+1:02d}"
            shots: list[dict[str, Any]] = []
            target_seconds_for_beat = max(15, beat["seconds"])
            remaining = target_seconds_for_beat
            shot_idx = 0
            # Slice into 5/10/15-second shots
            while remaining > 0 and shot_idx < 6:
                dur = 15 if remaining >= 15 else (10 if remaining >= 10 else 5)
                remaining -= dur
                shot_idx += 1
                shot_id = f"{ep_id}_sh{i*10+shot_idx:03d}"
                speakers = [c for c in chars_in_ep if c in char_lookup]
                speaker_id = speakers[shot_idx % max(1, len(speakers))] if speakers else (chars_in_ep[0] if chars_in_ep else "char_x")
                line_id = f"{shot_id}_l1"
                line_text = f"{char_lookup.get(speaker_id, {}).get('canonical_name', speaker_id)}：在第{i+1}场我必须说出真相。"
                line_seconds = 1.6 + (i % 3) * 0.2
                dialogues.append(
                    {
                        "line_id": line_id,
                        "speaker_char_id": speaker_id,
                        "text": line_text,
                        "emotion": "tense",
                        "prosody": "normal",
                        "seconds": line_seconds,
                        "source_spans": [(i * 64, i * 64 + 32)],
                    }
                )
                shots.append(
                    {
                        "shot_id": shot_id,
                        "intent": ["establish", "build", "turn", "climax", "resolve"][min(i, 4)],
                        "characters": [c for c in chars_in_ep[: 2]],
                        "location_id": episode["locations_present"][i % max(1, len(episode["locations_present"]))],
                        "mood": "tense" if i % 2 == 0 else "warm",
                        "estimated_seconds": dur,
                        "music_cue": "underscore" if i % 2 == 0 else "calm",
                        "sfx_cue": "",
                        "dialogue_line_ids": [line_id],
                        "key_action": f"{beat['summary']}-{shot_idx}",
                    }
                )
            scenes.append(
                {
                    "scene_id": scene_id,
                    "location_id": episode["locations_present"][i % max(1, len(episode["locations_present"]))],
                    "description": beat["summary"],
                    "shots": shots,
                }
            )
            cumulative += target_seconds_for_beat
        target = episode["target_seconds"]
        delta_pct = (cumulative - target) / max(1, target)
        out = {
            "episode_id": ep_id,
            "fountain_uri": f"local://scripts/{ep_id}.fountain",
            "scenes": scenes,
            "dialogues": dialogues,
            "narration": [],
            "timing": {
                "cumulative_seconds": cumulative,
                "target_seconds": target,
                "delta_pct": delta_pct,
            },
            "judge_scores": {"faithfulness": 0.92, "coverage": 0.91, "structure": 0.93},
        }
        return out

    # ----------------- StoryboardDirector -----------------
    def storyboard(self, *, script: dict[str, Any], style_sha: str, seed: int) -> dict[str, Any]:
        shots = []
        for sc in script["scenes"]:
            for _k, sh in enumerate(sc["shots"]):
                shots.append(
                    {
                        "shot_id": sh["shot_id"],
                        "scene_id": sc["scene_id"],
                        "sequence_index": len(shots),
                        "target_seconds": sh["estimated_seconds"],
                        "shot_size": ["MS", "CU", "WS", "ECU", "EWS"][len(shots) % 5],
                        "camera_angle": ["eye", "low", "high", "eye", "dutch"][len(shots) % 5],
                        "camera_movement": ["static", "pan", "dolly", "tracking", "tilt"][len(shots) % 5],
                        "lens_focal_mm": [35, 50, 85, 35, 24][len(shots) % 5],
                        "depth_of_field": ["medium", "shallow", "medium", "shallow", "deep"][len(shots) % 5],
                        "lighting_preset": "soft_key",
                        "palette_ref": ["#222", "#888"],
                        "weather": "clear",
                        "characters": [
                            {
                                "char_id": c,
                                "outfit_id": f"{c}_outfit_00",
                                "state_node_id": f"{c}_n0",
                            }
                            for c in sh["characters"][:2]
                        ],
                        "key_action": sh["key_action"],
                        "key_emotion": sh["mood"],
                        "mood": sh["mood"],
                        "music_cue": sh["music_cue"],
                        "sfx_cue": sh["sfx_cue"],
                        "prompt_brief": {
                            "clauses": [
                                f"location:{sh['location_id']}",
                                f"mood:{sh['mood']}",
                                f"key_action:{sh['key_action']}",
                                f"shot_size:{['MS','CU','WS','ECU','EWS'][len(shots) % 5]}",
                                "camera:static",
                                "palette:locked",
                                "characters_locked:true",
                                "max_2_chars:true",
                                f"duration:{sh['estimated_seconds']}",
                                "style:locked",
                            ]
                        },
                    }
                )
        return {
            "episode_id": script["episode_id"],
            "shots": shots,
            "continuity_score": 0.95,
        }
