"""Regression for cosmetic features; no broker or Internet used."""
import tempfile,unittest,copy
from pathlib import Path
from PIL import Image
from akira_studio import (DEFAULT,validate_studio,detect_expression,import_media,import_sprites,
                           UserCatalog,transform_wallpaper,LOCALES,UI_LABELS)
from settings import load_config,DEFAULT as APP_DEFAULT,save_config
from akira_expressions import get_catalog

class StudioTests(unittest.TestCase):
    def test_name_and_palette_invalid_rejected(self):
        item=copy.deepcopy(DEFAULT);item['brand_name']='Otro Nombre';self.assertEqual(validate_studio(item)['brand_name'],'Otro Nombre')
        item['brand_name']='../../hack'
        with self.assertRaises(ValueError):validate_studio(item)
        item=copy.deepcopy(DEFAULT);item['accent']='not-a-color'
        with self.assertRaises(ValueError):validate_studio(item)
    def test_default_design_is_akira_and_wallpaper_disabled(self):
        self.assertEqual(DEFAULT['theme'],'AKIRA Original')
        self.assertFalse(DEFAULT['wallpaper']['enabled'])
        self.assertFalse(DEFAULT['avatar']['active'])
        self.assertEqual(len(UI_LABELS['es']),8)
        self.assertGreaterEqual(len(LOCALES),8)
    def test_sprites_import_sort_and_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            a=root/'mi_perrito_parpadeo.png';b=root/'mi_perrito_habla.png'
            Image.new('RGBA',(64,64),(255,0,0,255)).save(a);Image.new('RGBA',(64,64),(0,0,255,255)).save(b)
            rows=import_sprites(root,[a,b]);self.assertEqual(len(rows),2)
            self.assertEqual([r['state'] for r in rows],['blink','talking'])
            catalog=UserCatalog(get_catalog(Path(__file__).resolve().parents[1]),{'entries':rows,'sequences':{}})
            self.assertEqual(catalog.choose('talking').id,rows[1]['id'])
            self.assertEqual(catalog.image(catalog.choose('idle'),88,88).size,(88,88))
            self.assertEqual(catalog.image(catalog.choose('talking'),88,88).size,(88,88))
    def test_sequences_move_without_using_broker(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);frames=[]
            for i in range(2):
                im=path/(f'habla_{i}.png');Image.new('RGBA',(32,32),(i*60,20,30,255)).save(im);frames.append(im)
            rows=import_sprites(path,frames)
            catalog=UserCatalog(get_catalog(Path(__file__).resolve().parents[1]),{'entries':rows,'sequences':{'talking':{'frames':[r['id'] for r in rows],'delay_ms':150,'loop':True}}})
            first=catalog.choose('talking');self.assertEqual(catalog.next_in_sequence('talking',99.8,first).id,first.id);next_frame=catalog.next_in_sequence('talking',100,first)
            self.assertIsNotNone(next_frame);self.assertNotEqual(first.id,next_frame.id)
            self.assertIsNone(catalog.next_in_sequence('talking',100.01,next_frame))
    def test_avatar_files_survive_release_migration(self):
        from migrate_v11_settings import restore_user_data
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);before=root/'r8';after=root/'r8-studio'
            src=before/'studio'/'avatars'/'talking.png';src.parent.mkdir(parents=True)
            Image.new('RGBA',(32,32),(255,255,255,255)).save(src)
            cfg=load_config(APP_DEFAULT)
            cfg['studio']['avatar'].update(active=True,entries=[{'id':'abcdef','path':str(src),'state':'talking','order':0}])
            cfg['studio']['wallpaper'].update(file=str(src),enabled=True,kind='image')
            before.mkdir(parents=True,exist_ok=True)
            save_config(cfg,before/'akira_config.json')
            after.mkdir(parents=True,exist_ok=True)
            (after/'akira_config.json').write_bytes((before/'akira_config.json').read_bytes())
            restore_user_data(before,None,after)
            self.assertEqual((after/'studio'/'avatars'/'talking.png').read_bytes(),src.read_bytes())
            restored=load_config(after/'akira_config.json')
            target=after/'studio'/'avatars'/'talking.png'
            # Windows TEMP may use RUNNER~1 while resolve() returns runneradmin.
            # Verify the migrated file identity and destination, not its spelling.
            for location in (restored['studio']['avatar']['entries'][0]['path'],restored['studio']['wallpaper']['file']):
                self.assertTrue(Path(location).samefile(target))
                self.assertTrue(Path(location).resolve().is_relative_to(after.resolve()))

    def test_wallpaper_resize_and_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);img=root/'sun.png';Image.new('RGB',(100,50),(255,0,0)).save(img)
            copied=import_media(root,img,'image');self.assertTrue(Path(copied).is_file())
            for fit in ('contain','cover','stretch'):
                c=copy.deepcopy(DEFAULT['wallpaper']);c['fit']=fit
                self.assertEqual(transform_wallpaper(Image.open(img),(180,140),c).size,(180,140))
            cfg=load_config(APP_DEFAULT);cfg['studio']['brand_name']='Mi Bot';cfg['studio']['wallpaper'].update(enabled=True,kind='image',file=copied)
            output=root/'config.json';save_config(cfg,output)
            self.assertEqual(load_config(output)['studio']['brand_name'],'Mi Bot')

if __name__=='__main__':unittest.main()
