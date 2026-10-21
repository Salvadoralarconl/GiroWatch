using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Accessibility;

public static class CamAccessibility {
    [DllImport("oleacc.dll")]
    private static extern int AccessibleObjectFromWindow(IntPtr hwnd, uint objectId, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out object result);
    [DllImport("oleacc.dll")]
    private static extern int AccessibleChildren(IAccessible parent, int start, int count,
        [Out, MarshalAs(UnmanagedType.LPArray, SizeParamIndex=2)] object[] children, out int obtained);

    private static IAccessible Root(long hwnd) {
        Guid iid=new Guid("618736E0-3C3D-11CF-810C-00AA00389B71");
        object result;
        int code=AccessibleObjectFromWindow(new IntPtr(hwnd),0xFFFFFFFC,ref iid,out result);
        if(code!=0 || result==null) throw new InvalidOperationException("Cam menu accessibility is unavailable.");
        return (IAccessible)result;
    }
    private static IEnumerable<Tuple<IAccessible,object>> Walk(IAccessible parent,int depth) {
        if(depth>8) yield break;
        yield return Tuple.Create(parent,(object)0);
        int count=parent.accChildCount;
        if(count<=0) yield break;
        object[] children=new object[count];int obtained;
        AccessibleChildren(parent,0,count,children,out obtained);
        for(int i=0;i<obtained;i++) {
            var accessible=children[i] as IAccessible;
            if(accessible!=null) {
                foreach(var item in Walk(accessible,depth+1)) yield return item;
            } else if(children[i] is int) {
                object child=parent.get_accChild(children[i]);
                accessible=child as IAccessible;
                if(accessible!=null) {
                    foreach(var item in Walk(accessible,depth+1)) yield return item;
                } else yield return Tuple.Create(parent,children[i]);
            }
        }
    }
    public static string Describe(long hwnd) {
        var names=new List<string>();
        foreach(var item in Walk(Root(hwnd),0)) {
            names.Add(item.Item1.get_accName(item.Item2)+" | "+item.Item1.get_accState(item.Item2));
        }
        return string.Join("\n",names);
    }
    public static void Run(long hwnd,string menuName,string runName) {
        var matches=new List<Tuple<IAccessible,object>>();
        bool foundMenu=false;
        foreach(var item in Walk(Root(hwnd),0)) {
            string name=item.Item1.get_accName(item.Item2);
            if(name==menuName) foundMenu=true;
            if(name==runName) matches.Add(item);
        }
        if(!foundMenu || matches.Count!=1) throw new InvalidOperationException("The configured menu and unique Run command could not be found. No action was sent.");
        var run=matches[0];
        if((Convert.ToInt32(run.Item1.get_accState(run.Item2)) & 1)!=0)
            throw new InvalidOperationException("Cam Run is disabled. No action was sent.");
        run.Item1.accDoDefaultAction(run.Item2);
    }
}
