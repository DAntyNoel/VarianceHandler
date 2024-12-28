from psd_tools import PSDImage
from PIL import Image
import json, copy

class VHError(Exception):
    pass

DEBUG = True

class Category:
    def __init__(self, name:str, mode:str='unk', subcategories:list['Category']=[], layers:list[str]=[], visibilities:list[bool]=[]):
        self.name = name
        if mode in ['all', 'or', 'one', 'same', 'unk']:
            self.mode = mode
        else:
            raise VHError(f"未知的模式: {mode}")
        self.subcategories = subcategories
        self.layers = layers
        if len(visibilities) == 0:
            self.visibilities = []
            self._build_visibility()
        else:
            self.visibilities = visibilities
        self.check_visibility()
    def __str__(self):
        return f"Category({self.name}, {self.mode}, {len(self.subcategories)} subs, {len(self.layers)} layers)"
    @classmethod
    def _sub_c_from_dict(cls, sub_c:list[dict, bool]) -> list['Category']:
        return [Category.from_dict(x[0]) for x in sub_c], [x[1] for x in sub_c]
    @classmethod
    def from_dict(cls, data:dict):
        sub_cs, visibilities = Category._sub_c_from_dict(data['subcategories'])
        return cls(data['name'], data['mode'], sub_cs, data['layers'], visibilities)
    def load_config(config_path):
        with open(config_path, 'r') as f:
            data:dict = json.load(f)
            return Category.from_dict(data)
    def _sub_c_to_dict(self) -> list[dict]:
        if len(self.subcategories) == 0:
            return [(layer, visible) for layer, visible in zip(self.layers, self.visibilities)]
        return [(x.to_dict(), visible) for x, visible in zip(self.subcategories, self.visibilities)]
    def to_dict(self):
        return {
            'name': self.name,
            'mode': self.mode,
            'subcategories': self._sub_c_to_dict(),
            'layers': self.layers
        }
    def save_config(self, output_path):
        data = self.to_dict()
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    def _build_visibility(self):
        if len(self.subcategories) == 0:
            self.visibilities = [False] * len(self.layers)
        else:
            self.visibilities = [False] * len(self.subcategories)
        
        if self.mode == 'all':
            self.visibilities = [True] * len(self.layers)
        elif self.mode == 'one':
            self.visibilities[0] = True
    def check_visibility(self):
        if self.mode == 'all':
            if len(self.visibilities) > 0 and not all(self.visibilities):
                raise VHError("该类别所有子类别及图层必须可见")
        elif self.mode == 'one':
            if not sum(1 for x in self.visibilities if x) == 1:
                raise VHError("该类别只能有一个子类别或图层可见")
        elif self.mode == 'same':
            if len(self.visibilities) > 0 and (not all(self.visibilities) or any(self.visibilities)):
                raise VHError(f"该类别所有子类别或图层必须同时可见或不可见: {self.visibilities}")
        
    
    def get_sub(self, c_name:str) -> tuple[int, 'Category']|None:
        for i, c in enumerate(self.subcategories):
            if c.name == c_name:
                return i, c
        return None
    def get_layer(self, layer_name:str) -> tuple[int, str]|None:
        for i, l in enumerate(self.layers):
            if l == layer_name:
                return i, l
        return None
    def get_all_layers(self) -> list[str]:
        if len(self.subcategories) == 0:
            return self.layers
        output = []
        for c in self.subcategories:
            output.extend(c.get_all_layers())
        return list(set(output))
    def get_all_visible_layers(self) -> list[str]:
        output = []
        if len(self.subcategories) > 0:
            for i, c in enumerate(self.subcategories):
                if c.visibilities[i]:
                    output.extend(c.get_all_visible_layers())
        else:
            for i, l in enumerate(self.layers):
                if self.visibilities[i]:
                    output.append(l)
        return list(set(output))
    def add_layer(self, layer:str):
        if len(self.subcategories) > 0:
            raise VHError("无法向包含子类别的类别添加图层")
        self.layers.append(layer)
        self.visibilities.append(False)
    def remove_layer(self, layer:str):
        if len(self.subcategories) > 0:
            raise VHError("无法从包含子类别的类别中删除图层")
        if layer in self.layers:
            self.layers.remove(layer)
            self.visibilities.pop(self.layers.index(layer))
        else:
            raise VHError(f"未找到名称为 {layer} 的图层")
    def add_sub(self, category_name, mode='unk'):
        new_c = Category(category_name, mode)
        self.subcategories = self.subcategories + [new_c]
        if len(self.subcategories) == 1:
            self.visibilities = [True]
        elif self.mode == 'all':
            self.visibilities.append(self.visibilities[0])
        else:
            self.visibilities.append(False)
        return new_c
    def remove_sub(self, category_name:str):
        for i, c in enumerate(self.subcategories):
            if c.name == category_name:
                self.subcategories.pop(i)
                if self.mode == 'one' and self.visibilities[i] == True:
                    self.visibilities[0] = True
                self.visibilities.pop(i)
                if len(self.subcategories) == 0:
                    self._build_visibility()
                return
    def set_visibility(self, visibility:bool, name:str):
        if self.mode == 'same':
            self.visibilities = [visibility] * len(self.visibilities)
        if self.mode == 'all':
            raise VHError("该类别所有子类别及图层必须可见，无法修改")
        if result := self.get_sub(name):
            if self.mode == 'one':
                if visibility:
                    self.visibilities = [False] * len(self.subcategories)
                    self.visibilities[result[0]] = True
                else:
                    self.visibilities[result[0]] = False
                    if not any(self.visibilities):
                        self.visibilities[0] = True
        elif name in self.layers:
            if len(self.subcategories) > 0:
                raise VHError("无法修改包含子类别的类别的图层可见性")
            self.visibilities[self.layers.index(name)] = visibility
        else:
            raise VHError(f"未找到名称为 {name} 的子类别或图层")

class PSDVarianceHandler:
    def __init__(self, psd_path=None, config=None):
        if config:
            # 从配置文件初始化
            with open(config, 'r', encoding='utf-8') as f:
                data:dict = json.load(f)
                self.root = Category.from_dict(data['root'])
                self.psd_path = data.get('psd_path')
            self.psd = PSDImage.open(self.psd_path)
            self.layer_dict:dict[str, PSDImage] = {}
            self._index_layers(self.psd)
        elif psd_path:
            # 初始化图层数据结构
            self.root = Category('root', 'all')
            self.psd_path = psd_path
            self.psd = PSDImage.open(psd_path)
            
            # 标号所有图层并生成图层字典
            self.layer_dict:dict[str, PSDImage] = {}
            self._index_layers(self.psd)
        else:
            raise VHError("必须提供 PSD 文件路径或配置文件路径")
        self._check_double_name()
    def save_config(self, output_path = 'vh_config.json'):
        """
        保存 PSD 配置
        """
        data = {
            'psd_path': self.psd_path,
            'root': self.root.to_dict(),
            '_layer_count': len(self.layer_dict.values()),
            '_layer_dict': {index: layer.name for index, layer in self.layer_dict.items()}
        }
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _index_layers(self, layer, prefix=''):
        """
        递归标号所有图层
        """
        index = prefix[:-1] if prefix else prefix
        if index:
            self.layer_dict[index] = layer
        if layer.is_group():
            for i, sublayer in enumerate(reversed(list(layer))):
                self._index_layers(sublayer, f'{prefix}{i}-')
    
    def _check_layer_idx_double_name(self, name=None):
        """
        检查是否有重名图层
        """
        names = [layer.name for layer in self.layer_dict.values()]

        if name:
            if name in names:
                raise VHError(f"图层名重复: {name}")
            return
        if len(names) != len(set(names)):
            # 找到重名图层
            name_count = {}
            for name in names:
                name_count[name] = name_count.get(name, 0) + 1
            double_names = [name for name, count in name_count.items() if count > 1]
            raise VHError(f"图层名重复: {double_names}")
    def _check_equal_level_category_double_name(self, parent_c:Category=None, name=None):
        """
        检查是否有重名的同级类别
        """
        equal_levels = [sub_c.name for sub_c in parent_c.subcategories]
        if name:
            if name in equal_levels:
                raise VHError(f"同级类别名重复: {name}\n({parent_c.name}: {equal_levels})")
            return
        if len(equal_levels) != len(set(equal_levels)):
            raise VHError(f"同级类别名重复: {equal_levels}")
        for sub_c in parent_c.subcategories:
            self._check_equal_level_category_double_name(sub_c)
    def _check_double_name(self, name=None, parent_c=None):
        '''检查是否有重名的图层或类别'''
        self._check_layer_idx_double_name(name)
        if not parent_c:
            parent_c = self.root
        self._check_equal_level_category_double_name(parent_c, name)
    
    def get_all_leaf_layer_name(self, layer_idx) -> list:
        """
        获取图层组内所有叶子图层名下标
        """
        if self.layer_dict[layer_idx].is_group():
            output = []
            for i in range(len(self.layer_dict[layer_idx])):
                output.extend(self.get_all_leaf_layer_name(f"{layer_idx}-{i}"))
            return output
        else:
            return [layer_idx]
    
    def parse_layer(self, layers:list) -> list:
        """预处理输入的图层名。如果输入的图层名是一个组，返回组内所有叶子图层名。"""
        output = []
        for layer in layers:
            if layer in self.layer_dict.keys():
                layer_idx = layer
                output.extend(self.get_all_leaf_layer_name(layer_idx))
            elif layer in [x.name for x in self.layer_dict.values()]:
                for k, v in self.layer_dict.items():
                    if v.name == layer:
                        layer_idx = k
                        break
                output.extend(self.get_all_leaf_layer_name(layer_idx))
            else:
                raise VHError(f"图层 {layer} 不存在")
        return list(set(output))
    
    def copy_psd(self, visible_layer_idxs=None) -> PSDImage:
        """生成psd文件的复制，并且将所有图层组设为可见，所有叶子图层设为不可见，然后根据输入的图层名列表设置可见图层"""
        visibel_layer_names = set(self.layer_dict[x].name for x in visible_layer_idxs) if visible_layer_idxs else set()
        psd = copy.deepcopy(self.psd)
        def handle_layer(layer):
            if layer.is_group():
                layer.visible = True
                for sublayer in layer:
                    handle_layer(sublayer)
            else:
                layer.visible = False
                if layer.name in visibel_layer_names:
                    layer.visible = True
        for layer in psd:
            handle_layer(layer)
        return psd
            
    def save_png(self, output_path=None) -> Image:
        """
        保存 PSD 文件为 PNG
        """
        visible_layers_idx = self.get_all_visible_layers(original=True)
        if DEBUG: print(f"可见图层: {[self.layer_dict[layer_idx].name for layer_idx in visible_layers_idx]}")
        new_psd = self.copy_psd(visible_layers_idx)
        image = new_psd.composite(force=True)
        if output_path:
            image.save(output_path)
        return image

    def get_all_visible_layers(self, original=False):
        """
        根据root返回所有可见图层
        """
        # visible_layers = set(visible_layers)
        visible_layers = self.root.get_all_visible_layers()
        parsed_layer_names = self.parse_layer(visible_layers)
        for layer_idx in parsed_layer_names:
            layer = self.layer_dict[layer_idx]
            if DEBUG: print(f"{layer.name}: 设置图层 {layer_idx}({layer.name}) 可见")
            visible_layers.add(layer_idx)

        if original:
            return visible_layers
        return [self.layer_dict[layer_idx] for layer_idx in visible_layers]
    
    ### Category ###
    def add_sub_c_to_category(self, category_dir_name:list[str], sub_c_names:list[str], mode:str):
        if len(category_dir_name) == 1:
            if category_dir_name[0] == 'root':
                assert mode == 'all'
                for sub_c_name in sub_c_names:
                    self.root.add_sub(sub_c_name)
                return
        now = self.root
        for c_name in category_dir_name:
            if result := now.get_sub(c_name):
                now = result[1]
                if now.name == category_dir_name[-1]:
                    if now.mode == 'unk':
                        if mode in ['all', 'or', 'one', 'same']:
                            now.mode = mode
                        else:
                            raise VHError(f"未知的模式: {mode}")
                    elif now.mode != mode:
                        if DEBUG: print(f"类别 {c_name} 的模式不匹配: {now.mode} != {mode}")
                        else: raise VHError(f"类别 {c_name} 的模式不匹配: {now.mode} != {mode}")
                    for sub_c_name in sub_c_names:
                        now.add_sub(sub_c_name)
                    if now.mode == 'same':
                        if mode in ['all', 'or', 'one']:
                            now.mode = mode
                        else:
                            raise VHError(f"未知的模式: {mode}")
                    elif now.mode != mode:
                        if DEBUG: print(f"类别 {c_name} 的模式不匹配: {now.mode} != {mode}")
                        else: raise VHError(f"类别 {c_name} 的模式不匹配: {now.mode} != {mode}")
            else:
                raise VHError(f"未找到名称为 {c_name} 的子类别: {category_dir_name}")
    def build_category_from_txt(self, txt_path:str):
        with open(txt_path, 'r') as f:
            lines = f.readlines()
        for line in lines:
            # Sample line: 'all:root-A:B C D E\n'
            
            line = line.replace('：',':')
            mode, category, layers = line.strip().split(':')
            category = category.strip().split('-')
            layers = layers.strip().split(' ')
            self.add_sub_c_to_category(category, layers, mode)
            json.dump(self.root.to_dict(), open('test.json', 'w'), indent=2, ensure_ascii=False)
    def get_Categories(self, target_names:str|list[str], search_mode:int=0) -> list[Category]:
        '''Search mode = 0 represents easy search, which means target_names is ordered from root to leaf.'''
        if isinstance(target_names, str):
            target_names = target_names.split('-')
        ret = []
        if search_mode == 0:
            now = self.root
            for c_name in target_names:
                if result := now.get_sub(c_name):
                    now = result[1]
                    ret.append(now)
                else:
                    raise VHError(f"未找到名称为 {c_name} 的子类别: {target_names}")
            return ret
        else:
            for c_name in target_names:
                # DFS search on the psd tree
                def dfs_search(category:Category, target_name):
                    if category.name == target_name:
                        return category
                    for sub_c in category.subcategories:
                        if result := dfs_search(sub_c, target_name):
                            return result
                    return None
                if result := dfs_search(self.root, c_name):
                    ret.append(result)
                else:
                    raise VHError(f"子类别 {c_name} 不存在！From: {target_names}")
            return ret

if __name__ == '__main__':
    vh = PSDVarianceHandler('1.psd')
    txt_path = '0.txt'
    vh.build_category_from_txt(txt_path)
    vh.save_config('vh_config.json')