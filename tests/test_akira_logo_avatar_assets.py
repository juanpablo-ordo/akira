from pathlib import Path
from PIL import Image
from akira_live2d import SPRITE_MAP

def test_all_avatar_expression_sprites_are_present_and_in_same_canvas():
    root=Path(__file__).resolve().parents[1]
    sprites={}
    for name in set(SPRITE_MAP.values()):
        path=root/'assets'/'vtuber'/name
        assert path.is_file(), name
        with Image.open(path) as im:
            assert im.size == (512,512)
            assert im.mode == 'RGBA'
            assert im.getextrema()[3] == (0,255)
            sprites[name]=im.tobytes()
    assert len(set(sprites.values())) >= 8

def test_original_akira_logo_is_available_and_ico():
    root=Path(__file__).resolve().parents[1]
    with Image.open(root/'assets'/'akira.png') as png:
        assert png.size[0] >=512 and png.size[1]>=512
    with Image.open(root/'assets'/'akira.ico') as ico:
        assert ico.format == 'ICO'


def test_avatar_reacts_to_messages_without_affecting_strategy():
    from akira_live2d import expression_for_reply
    assert expression_for_reply('Estoy revisando indicadores de BTC') == 'analyzing'
    assert expression_for_reply('Error: sin conexión a MT5') == 'alert'
    assert expression_for_reply('Ganancia confirmada') == 'happy'
    assert expression_for_reply('Hola, ¿cómo estás?') == 'talking'
