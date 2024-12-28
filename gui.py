import os, json
import tkinter as tk
from tkinter import ttk, Menu, filedialog, messagebox
from PIL import Image, ImageTk

import api
from api import (
    PSDVarianceHandler, Category, 
    VHError, NotAllowedError,
    DEBUG
)

current_menu = None
root = None

def warning(message):
    messagebox.showwarning("警告", message)

def error(message):
    messagebox.showerror("错误", message)

def mark_unsaved():
    global root
    if not root.title().startswith("*"):
        root.title("*" + root.title())

def mark_saved():
    global root
    if root.title().startswith("*"):
        root.title(root.title()[1:])

def check_unsaved_changes_then_quit():
    global root
    if root.title().startswith("*"):
        if messagebox.askyesno("确认退出", "有未保存的更改。是否确认退出？"):
            root.destroy()
        else:
            return
    else:
        root.destroy()



def parse_category_name(category_name:str) -> tuple[str, str, bool]:
    '''解析类别名称，返回类别名称、模式和是否显示的元组'''
    if category_name.endswith('*'):
        visibility = True
        category_name = category_name[:-1]
    else:
        visibility = False
    if category_name.endswith(')'):
        mode = category_name.split('(')[-1][:-1]
        category_name = category_name.split('(')[0].strip()
    else:
        raise VHError(f"Invalid category name: {category_name}")
    return category_name, mode, visibility

#### GUI 主界面功能 ####
def close_menu(event):
    global current_menu
    if current_menu:
        current_menu.unpost()
        current_menu = None
#### GUI 主界面功能 END####

#### 差分列表功能 ####
### Category Menu Function ###
def rename_category(tree:ttk.Treeview, item_id:str, category_name:str, vh:PSDVarianceHandler):
    if DEBUG:
        print(f"Rename category {category_name}")
    c_name, c_mode, c_visibility = parse_category_name(category_name)
    rename_window = tk.Toplevel()
    rename_window.title(f"重命名 {c_name}")

    tk.Label(rename_window, text="新名称：").pack(pady=10)
    new_name_entry = tk.Entry(rename_window)
    new_name_entry.pack(pady=5)

    def save_new_name():
        new_name = new_name_entry.get()
        if new_name:
            try:
                vh._check_double_name(new_name, parent_c=vh.get_Categories(_get_all_parents(tree, item_id))[-1])
                api.rename_sub_c(vh, c_name, _get_all_parents(tree, item_id), new_name)
                # Rename the item in the treeview
                mark_unsaved()
                tree.item(item_id, text=f"{new_name} ({c_mode}){'*' if c_visibility else ''}")
            except VHError as e:
                error(str(e))
                return
            except NotAllowedError as e:
                warning('禁止操作!\n'+str(e))
                return
            else:
                rename_window.destroy()
        else:
            warning("新名称不能为空！")

    tk.Button(rename_window, text="保存", command=save_new_name).pack(pady=10)

def reverse_visibility(tree:ttk.Treeview, item_id:str, category_name:str, vh:PSDVarianceHandler):
    if DEBUG:
        print(f"Reverse visibility of {category_name}")
    c_name, c_mode, c_visibility = parse_category_name(category_name)
    try:
        parents = _get_all_parents(tree, item_id)
        api.reverse_visibility(vh, c_name, parent_names=parents)
        # Change the item in the treeview
        parent_id = tree.parent(item_id)
        parent_c = vh.get_Categories(parents)[-1] if len(parents) > 0 else vh.root
        for child in tree.get_children(parent_id):
            tree.delete(child)
        for sub_c, v in zip(parent_c.subcategories, parent_c.visibilities):
            build_tree(tree, parent_id, sub_c, v)
        # mark_unsaved()
    except VHError as e:
        error(str(e))
    except NotAllowedError as e:
        warning('禁止操作!\n'+str(e))
### Category Menu Function END ###

def create_menu(tree:ttk.Treeview, event:tk.Event, vh:PSDVarianceHandler):
    global current_menu
    selected_item = tree.identify('item', event.x, event.y)
    tree.selection_set(selected_item)
    category_name = tree.item(selected_item, 'text')

    current_menu = Menu(tree, tearoff=0)
    if category_name:
        current_menu.add_command(label=f"Information about {category_name}", command=lambda: print(f"Selected: {category_name}"))
        current_menu.add_command(label=f"{'隐藏' if category_name.endswith('*') else '显示'} 图层/分类", command=lambda: reverse_visibility(tree, selected_item, category_name, vh))
        current_menu.add_command(label=f"重命名…", command=lambda: rename_category(tree, selected_item, category_name, vh))
        current_menu.add_separator()
    current_menu.add_command(label="Option 1", command=lambda: print("Option 1 selected"))
    current_menu.add_command(label="Option 2", command=lambda: print("Option 2 selected"))
    current_menu.post(event.x_root, event.y_root)

def build_tree(tree:ttk.Treeview, parent:str, category:Category, display:bool):
    display_name = f"{category.name} ({category.mode})"
    if display:
        display_name += '*'
    item_id = tree.insert(parent, 'end', text=display_name)
    if category.mode == 'all':
        tree.item(item_id, open=True)
    if len(subcategory := category.subcategories) > 0:
        for subcategory, v in zip(subcategory, category.visibilities):
            build_tree(tree, item_id, subcategory, v)
    elif len(layers := category.layers) > 0:
        for layer, v in zip(layers, category.visibilities):
            display_name = layer
            if v:
                display_name += '*'
            tree.insert(item_id, 'end', text=display_name)

def _get_all_parents(tree:ttk.Treeview, item_id):
    parents = []
    parent_id = tree.parent(item_id)
    while parent_id:
        selected_item = tree.item(parent_id, 'text')
        c_name, _, _ = parse_category_name(selected_item)
        parents.append(c_name)
        parent_id = tree.parent(parent_id)
    return list(reversed(parents))

def on_tree_double_click(event, tree:ttk.Treeview, vh:PSDVarianceHandler):
    item_id = tree.identify('item', event.x, event.y)
    if item_id:
        category_name = tree.item(item_id, 'text')
        parent_names = _get_all_parents(tree, item_id)
        if DEBUG: print(f"Double-clicked on: {category_name}, Parents: {parent_names}")
        reverse_visibility(tree, item_id, category_name, vh)
#### 差分列表功能 END ####

#### GUI 顶部按钮功能 ####
def refresh_tree(tree:ttk.Treeview, root_category:Category):
    for item in tree.get_children():
        tree.delete(item)
    for sub_c in root_category.subcategories:
        build_tree(tree, "", sub_c, False)

def refresh_all(tree: ttk.Treeview, canvas: tk.Canvas, root_category: Category):
    refresh_tree(tree, root_category)
    canvas.delete("all")
    print("Treeview refreshed and Canvas cleared")

def show_image(canvas:tk.Canvas, image_path:str=os.path.join('resources', 'output1.png')):
    image = Image.open(image_path)
    canvas_width = 700
    canvas_height = 700
    
    image_width, image_height = image.size
    scale = min(canvas_width / image_width, canvas_height / image_height)
    new_width = int(image_width * scale)
    new_height = int(image_height * scale)
    
    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    image_tk = ImageTk.PhotoImage(resized_image)
    
    canvas.delete("all")
    canvas.create_image(0, 0, anchor='nw', image=image_tk)
    canvas.image = image_tk  # 保存引用以防止图像被垃圾回收
    canvas.original_image = image

def save_image(canvas: tk.Canvas):
    if not hasattr(canvas, 'original_image') or not canvas.original_image:
        print("No image to save")
        warning("没有选择图片！")
        return
    file_path = filedialog.asksaveasfilename(defaultextension=".png",
                                             filetypes=[("PNG files", "*.png"), ("All files", "*.*")])
    if file_path:
        canvas.original_image.save(file_path)
        print(f"Image saved to {file_path}")
#### GUI 顶部按钮功能 END ####

def main(vh:PSDVarianceHandler):
    global root
    root_category = vh.root
    root = tk.Tk()
    root.title("差分预览")
    root.geometry("950x770")

    botton_frame = tk.Frame(root)
    botton_frame.pack(fill=tk.X, pady=10)
    buttons = ['刷新', '预览', '保存', '退出']
    commands = [
        lambda: refresh_all(tree, canvas, root_category),
        lambda: show_image(canvas), 
        lambda: save_image(canvas), 
        lambda: check_unsaved_changes_then_quit()
    ]
    for b_text, cmd in zip(buttons, commands):
        tk.Button(botton_frame, text=b_text, width=10, height=2, command=cmd).pack(side=tk.LEFT, padx=10)
    
    content_frame = tk.Frame(root)
    content_frame.pack(expand=True, fill=tk.BOTH)

    tree_frame = tk.Frame(content_frame, width=100, height=700)
    tree_frame.pack(side=tk.LEFT, padx=5, fill=tk.Y)

    tree = ttk.Treeview(tree_frame)
    tree.pack(expand=True, fill=tk.BOTH)

    canvas_frame = tk.Frame(content_frame, width=700, height=700)
    canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

    canvas = tk.Canvas(canvas_frame, bg='white', width=700, height=700)
    canvas.pack(expand=True, fill=tk.BOTH)

    tree.bind('<Double-1>', lambda event: on_tree_double_click(event, tree, vh))
    tree.bind("<Button-3>", lambda event: create_menu(tree, event, vh))

    root.bind("<Button-1>", close_menu)
    root.protocol("WM_DELETE_WINDOW", check_unsaved_changes_then_quit)

    for sub_c in root_category.subcategories:
        build_tree(tree, "", sub_c, True)

    root.mainloop()

if __name__ == "__main__":
    vh = PSDVarianceHandler(config=os.path.join('resources', 'vh_config.json'))
    main(vh)
