from PIL import Image, ImageTk
from typing import Any

from psd_handler import PSDVarianceHandler, Category, DEBUG, VHError, PSDImage

class NotAllowedError(Exception):
    pass

def reverse_visibility(vh:PSDVarianceHandler, 
                       target_name:str, 
                       parent_names:list[str]):
    '''parent_names: list of parent names from the root to the target category (not included)'''
    if DEBUG:
        print(f"Reverse visibility for {target_name} with parents: {parent_names}")
    categories = vh.get_Categories(parent_names)
    final_c = categories[-1]
    if final_c.mode == 'all':
        raise NotAllowedError(f"Cannot change visibility of 'all' category {final_c.name}")
    if final_c.mode == 'unk':
        raise VHError(f"Unknown mode for category {final_c.name}")
    
    if result := final_c.get_sub(target_name):
        idx = result[0]
    elif result := final_c.get_layer(target_name):
        idx = result[0]
    else:
        raise VHError(f"Category {target_name} not found in {parent_names}")

    if final_c.mode == 'or':
        final_c.visibilities[idx] = not final_c.visibilities[idx]
    elif final_c.mode == 'one':
        if idx == 0 and final_c.visibilities[0]:
            raise NotAllowedError(f"Cannot hide the only visible layer in 'one' category {final_c.name}")
        final_c.visibilities = [False] * len(final_c.visibilities)
        final_c.visibilities[idx] = True
    elif final_c.mode == 'same':
        final_c.visibilities = [not final_c.visibilities[idx]] * len(final_c.visibilities)
    else:
        raise VHError(f"Unknown mode({final_c.mode}) for category {final_c.name}")
    
def get_visible_image(vh:PSDVarianceHandler) -> Image:
    return vh.save_png()

def get_specific_layers_image(vh:PSDVarianceHandler, 
                              target_names:str|list[str], 
                              visible:bool=False
                              ) -> Image:
    '''parent_names: list of parent names from the root to the target category (not included)
    visible: if True, only visible layers will be shown'''
    if DEBUG:
        print(f"Get specific layers image for {target_names}")
    layer_idxs = [t for t in target_names if t in vh.layer_dict.keys()]
    others = [t for t in target_names if t not in vh.layer_dict.keys()]
    categories = vh.get_Categories(others, search_mode=1)
    for c in categories:
        if visible:
            if result := c.get_all_visible_layers():
                layer_idxs.extend(result)
        else:
            if result := c.get_all_layers():
                layer_idxs.append(result)
    psd_image = vh.copy_psd(layer_idxs)
    return psd_image.composite(force=True)


def get_psd_layers_dict(vh:PSDVarianceHandler, 
                        search_root:str|PSDImage|None=None,
                        show_image:bool=False
                        ) -> tuple[dict[str, list[dict]|None], Any]:
    '''search_root 代表搜索的根节点，必须是图层下标或图层本身，如果为None则返回全部图层
    show_image 代表是否返回合成图像
    
    返回值：(dict, PIL.Image)，其中图片是所有图层的合成图，dict是图层的字典，具有嵌套结构。'''
    if DEBUG:
        print(f"Get PSD layers dict for {search_root}")
    if search_root is None:
        search_root = vh.psd
    if isinstance(search_root, str):
        if search_root not in vh.layer_dict.keys():
            raise VHError(f"Layer {search_root} not found in PSD!")
        search_root = vh.layer_dict[search_root]
    if show_image:
        image = search_root.composite()
    else:
        image = None
    
    return {search_root.name: [
        get_psd_layers_dict(vh, x, show_image=False)[0] for x in search_root
    ]}, image

def rename_sub_c(vh:PSDVarianceHandler, 
                 target_name:str, 
                 parent_names:list[str], 
                 new_name:str):
    '''parent_names: list of parent names from the root to the target category (not included)'''
    if DEBUG:
        print(f"Rename {target_name} to {new_name} with parents: {parent_names}")
    categories = vh.get_Categories(parent_names)
    final_c = categories[-1]
    if result := final_c.get_sub(target_name):
        target_c = result[1]
        target_c.name = new_name
    elif result := final_c.get_layer(target_name):
        raise NotAllowedError(f"不能修改底层图层名！{target_name}")
    else:
        raise VHError(f"Category {target_name} not found in {parent_names}")

def add_sub_c(vh:PSDVarianceHandler, 
              target_name:str, 
              parent_names:list[str], 
              new_c_name:str,
              new_c_mode:str='unk'
              ) -> Category:
    '''parent_names: list of parent names from the root to the target category (not included)'''
    if DEBUG:
        print(f"Add sub-category {new_c_name} to {target_name} with parents: {parent_names}")
    vh._check_layer_idx_double_name(new_c_name)
    categories = vh.get_Categories(parent_names)
    final_c = categories[-1]
    if result := final_c.get_sub(target_name):
        target_c = result[1]
    elif result := final_c.get_layer(target_name):
        raise NotAllowedError(f"不能在底层图层下添加子类别！{target_name}")
    else:
        raise VHError(f"Category {target_name} not found in {parent_names}")
    
    return target_c.add_sub(new_c_name, new_c_mode)

def delete_sub_c(vh:PSDVarianceHandler,
                 target_name:str,
                 parent_names:list[str]):
    '''parent_names: list of parent names from the root to the target category (not included)'''
    if DEBUG:
        print(f"Delete sub-category {target_name} with parents: {parent_names}")
    categories = vh.get_Categories(parent_names)
    final_c = categories[-1]
    if result := final_c.get_sub(target_name):
        target_c = result[1]
    elif result := final_c.get_layer(target_name):
        raise NotAllowedError(f"不能删除底层图层！{target_name}")
    else:
        raise VHError(f"Category {target_name} not found in {parent_names}")
    
    final_c.subcategories.remove(target_c)

def change_mode(vh:PSDVarianceHandler, 
                target_name:str, 
                parent_names:list[str], 
                new_mode:str):
    '''parent_names: list of parent names from the root to the target category (not included)'''
    if DEBUG:
        print(f"Change mode of {target_name} to {new_mode} with parents: {parent_names}")
    if new_mode not in ('all', 'or', 'one', 'same'):
        raise NotAllowedError(f"不允许的模式：{new_mode}！")
    categories = vh.get_Categories(parent_names)
    final_c = categories[-1]
    if result := final_c.get_sub(target_name):
        target_c = result[1]
    elif result := final_c.get_layer(target_name):
        raise NotAllowedError(f"不能修改底层图层的模式！{target_name}")
    else:
        raise VHError(f"Category {target_name} not found in {parent_names}")
    
    target_c.mode = new_mode
    target_c.visibilities = [False] * len(target_c.visibilities)
    if new_mode == 'all':
        target_c.visibilities = [True] * len(target_c.visibilities)
    elif new_mode == 'one':
        target_c.visibilities[0] = True

def add_layer(vh:PSDVarianceHandler, 
              target_name:str, 
              parent_names:list[str], 
              new_layer_name:str):
    '''parent_names: list of parent names from the root to the target category (not included)'''
    if DEBUG:
        print(f"Add layer {new_layer_name} to {target_name} with parents: {parent_names}")
    vh._check_layer_idx_double_name(new_layer_name)
    if new_layer_name not in vh.layer_dict.keys():
        raise VHError(f"Layer {new_layer_name} not found in PSD!")
    categories = vh.get_Categories(parent_names + [target_name])
    final_c = categories[-1]
    final_c.add_layer(new_layer_name)

def delete_layer(vh:PSDVarianceHandler,
                 target_name:str,
                 parent_names:list[str]):
    '''parent_names: list of parent names from the root to the target category (not included)'''
    if DEBUG:
        print(f"Delete layer {target_name} with parents: {parent_names}")
    categories = vh.get_Categories(parent_names)
    final_c = categories[-1]
    if target_name not in final_c.layers:
        raise VHError(f"Layer {target_name} not found in {parent_names}")
    final_c.layers.remove(target_name)

    