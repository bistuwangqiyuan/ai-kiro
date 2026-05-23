# 本地 BGM 曲库（国内默认）

> 本目录用于无需 ElevenLabs 等境外 API 时的本地音乐方案。
> `LocalMusicLibraryAdapter` 会根据题材/情绪从对应子目录挑曲并用 ffmpeg 裁切到目标时长。

## 目录约定

```
assets/bgm/
├── ancient/      # 古风
├── modern/       # 都市
├── sweet_pet/    # 甜宠
├── suspense/     # 悬疑
├── xuanhuan/     # 玄幻
├── campus/       # 校园
├── urban/        # 都市
├── xianxia/      # 仙侠
└── _default/     # 兜底曲库
```

每个目录放任意数量 mp3 / wav / m4a / flac / ogg 文件，命名随意。

## 推荐免版权曲库来源

为了零授权风险，**请只使用 CC0 / Public Domain / Royalty-Free** 来源：

| 来源 | 链接 | 备注 |
|---|---|---|
| Pixabay Music | <https://pixabay.com/music/> | 全 CC0，中文古风/玄幻很多 |
| 网易云音乐 - 创作工坊免版税池 | <https://music.163.com/> 创作中心 | 国内首选 |
| Free Music Archive | <https://freemusicarchive.org/> | CC0 / CC-BY |
| ccMixter | <http://ccmixter.org/> | CC-BY |
| YouTube Audio Library | YouTube Studio 内置 | 部分免版权 |

> 在 `_default/` 至少放 1-2 首 1-3 分钟的中性氛围曲，作为兜底。

## 如果不放任何曲

`LocalMusicLibraryAdapter` 会生成一段 `-50dBFS` 极低能量正弦波占位（几乎无声），
不会让生产链中断，视频依旧能正常出片，只是 BGM 静音。

## 切回 ElevenLabs

填好 `.env` 中 `ELEVENLABS_API_KEY`，将 `config/system.yaml` 中的：

```yaml
live:
  music:
    primary: "elevenlabs"
  sfx:
    primary: "elevenlabs"
```

即可。
