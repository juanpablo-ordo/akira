"""Update existing table rows while preserving selection and scroll position."""


def sync_table(tree,rows):
    rows=list(rows);wanted={str(key) for key,values,tags in rows}
    current=list(tree.get_children());changed_order=False
    old=getattr(tree,'_akira_rows',{})
    cache={}
    for key in current:
        if key not in wanted:tree.delete(key);changed_order=True
    for index,(key,values,tags) in enumerate(rows):
        key=str(key);value=(tuple(values),tuple(tags));cache[key]=value
        if not tree.exists(key):tree.insert('','end',iid=key,values=values,tags=tags);changed_order=True
        elif old.get(key)!=value:tree.item(key,values=values,tags=tags)
    expected=[str(key) for key,_,_ in rows]
    if list(tree.get_children())!=expected:
        for index,key in enumerate(expected):tree.move(key,'',index)
        changed_order=True
    tree._akira_rows=cache
    return changed_order
