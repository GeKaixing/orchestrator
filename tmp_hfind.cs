using System;
using System.Runtime.InteropServices;
using System.Text;

namespace HF {
  public class F {
    [DllImport("ntdll.dll")]
    static extern int NtQuerySystemInformation(int cls, IntPtr buf, int len, out int ret);

    [StructLayout(LayoutKind.Sequential)]
    public struct SE {
      public ushort UniqueProcessId;
      public ushort CreatorBackTraceIndex;
      public byte ObjectTypeIndex;
      public byte HandleAttributes;
      public ushort HandleValue;
      public IntPtr Object;
      public uint GrantedAccess;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct US {
      public ushort Length;
      public ushort MaximumLength;
      public IntPtr Buffer;
    }

    [DllImport("kernel32.dll")]
    static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")]
    static extern IntPtr GetCurrentProcess();
    [DllImport("ntdll.dll")]
    static extern int NtDuplicateObject(IntPtr src, IntPtr h, IntPtr dst, out IntPtr dup, uint da, uint oa, uint opts);
    [DllImport("ntdll.dll")]
    static extern int NtQueryObject(IntPtr h, int cls, IntPtr buf, int len, out int needed);

    static string FileName(IntPtr dup) {
      int needed = 0;
      NtQueryObject(dup, 1, IntPtr.Zero, 0, out needed);
      if (needed <= 0) return "";
      IntPtr buf = Marshal.AllocHGlobal(needed);
      try {
        int req = 0;
        if (NtQueryObject(dup, 1, buf, needed, out req) == 0) {
          var us = Marshal.PtrToStructure<US>(buf);
          return Marshal.PtrToStringUni(us.Buffer);
        }
      } finally { Marshal.FreeHGlobal(buf); }
      return "";
    }

    static string ProcName(int pid) {
      IntPtr h = OpenProcess(0x1000, false, pid);
      if (h == IntPtr.Zero) return "";
      var sb = new StringBuilder(1024);
      int n = 1024;
      try { if (QueryFullProcessImageName(h, 0, sb, ref n)) { CloseHandle(h); return sb.ToString(); } } catch {}
      CloseHandle(h);
      return "";
    }

    [DllImport("kernel32.dll")]
    static extern bool QueryFullProcessImageName(IntPtr h, int flags, StringBuilder sb, ref int size);

    public static int Main(string[] args) {
      string target = System.IO.Path.GetFullPath(args[0]).ToLowerInvariant().Replace("/", "\\");
      bool x64 = IntPtr.Size == 8;
      int entrySize = x64 ? 32 : 16;
      uint size = 1024 * 1024;
      IntPtr buf = Marshal.AllocHGlobal((int)size);
      try {
        while (true) {
          int ret;
          int st = NtQuerySystemInformation(16, buf, (int)size, out ret);
          if (st == 0) break;
          if (st == unchecked((int)0xC0000005) || ret == 0) { /* invalid/handle table grows */ }
          if (st == -1073741820) {
            Marshal.FreeHGlobal(buf); size = (uint)ret; buf = Marshal.AllocHGlobal((int)size); continue;
          }
          return 2;
        }
        int count = Marshal.ReadInt32(buf);
        int start = x64 ? 8 : 4;
        var self = GetCurrentProcess();
        for (int i = 0; i < count; i++) {
          IntPtr p = new IntPtr(buf.ToInt64() + start + (long)i * entrySize);
          int pid = Marshal.ReadInt16(p, 0);
          ushort hval = (ushort)Marshal.ReadInt16(p, 6);
          IntPtr dup;
          IntPtr hp = OpenProcess(0x1000, false, pid);
          if (hp == IntPtr.Zero) continue;
          int st = NtDuplicateObject(hp, (IntPtr)hval, self, out dup, 0, 0, 0);
          CloseHandle(hp);
          if (st != 0) continue;
          string name = FileName(dup);
          CloseHandle(dup);
          if (name.Length == 0) continue;
          string n = name.ToLowerInvariant();
          if (n.StartsWith("\\device\\") && n.Contains(target)) {
            Console.WriteLine("HIT PID=" + pid + " " + ProcName(pid) + " handle=0x" + hval.ToString("x") + " -> " + name);
          }
        }
      } finally { Marshal.FreeHGlobal(buf); }
      return 0;
    }
  }
}