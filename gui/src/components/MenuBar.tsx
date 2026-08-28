// 菜单栏：文件 / 剪辑 / 字幕 / 工具 —— 点击打开下拉（更稳定，避免 CSS hover 闪退）。

import { useEffect, useRef, useState } from "react";

export interface MenuActions {
  onOpenProject: () => void;
  onNewProject: () => void;
  onShowHelp: () => void;
  onImport: (files: FileList) => void;
  onImportJianying: () => void;
  onRender: () => void;
  onExport: () => void;
  onExportRange: () => void;
  onExportPackage: () => void;
  onCommit: () => void;
  onSplit: () => void;
  onTrimHead: () => void;
  onTrimTail: () => void;
  onSilenceRemove: () => void;
  onDenoise: () => void;
  onLoudness: () => void;
  onAddSubtitle: () => void;
  onGenerateSubtitles: () => void;
  onRegionMode: () => void;
  hasClip: boolean;
  regionMode: boolean;
}

interface Item {
  label: string;
  action?: keyof MenuActions;
  disabled?: boolean;
  divider?: boolean;
}

export default function MenuBar(props: MenuActions) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const clipItems: Item[] = [
    { label: "在播放头切分", action: "onSplit" },
    { label: "头裁 0.5s", action: "onTrimHead" },
    { label: "尾裁 0.5s", action: "onTrimTail" },
    { label: "", divider: true },
    { label: "去停顿/气口", action: "onSilenceRemove" },
    { label: "降噪", action: "onDenoise" },
    { label: "响度分析", action: "onLoudness" },
  ];

  const menus: Array<{ name: string; items: Item[] }> = [
    {
      name: "文件",
      items: [
        { label: "打开工程…", action: "onOpenProject" },
        { label: "新建工程…", action: "onNewProject" },
        { label: "", divider: true },
        { label: "导入素材…", action: "onImport" },
        { label: "导入剪映工程…", action: "onImportJianying" },
        { label: "", divider: true },
        { label: "渲染预览", action: "onRender" },
        { label: "导出成片…", action: "onExport" },
        { label: "导出选区（I/O 点）…", action: "onExportRange" },
        { label: "发布包导出（成片+封面+报告）", action: "onExportPackage" },
        { label: "存版本", action: "onCommit" },
      ],
    },
    { name: "剪辑", items: clipItems.map((i) => ({ ...i, disabled: i.divider ? undefined : !props.hasClip })) },
    {
      name: "字幕",
      items: [
        { label: "在播放头加字幕", action: "onAddSubtitle" },
        { label: "从转写自动生成整轨字幕", action: "onGenerateSubtitles" },
      ],
    },
    {
      name: "帮助",
      items: [{ label: "快捷键清单", action: "onShowHelp" }],
    },
    {
      name: "工具",
      items: [{ label: props.regionMode ? "退出框选" : "框选去水印", action: "onRegionMode" }],
    },
  ];

  const click = (item: Item) => {
    if (!item.action || item.disabled) return;
    if (item.action === "onImport") {
      const input = document.createElement("input");
      input.type = "file";
      input.multiple = true;
      input.accept = "video/*,audio/*,image/*";
      input.onchange = () => input.files?.length && props.onImport(input.files);
      input.click();
      return;
    }
    (props[item.action] as () => void)();
    setOpenMenu(null);  // 点击后关闭菜单
  };

  // 点外面关闭
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpenMenu(null);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  return (
    <div className="menubar" ref={rootRef}>
      {menus.map((m) => (
        <div key={m.name} className="menu">
          <span
            className="menu-name"
            onClick={() => setOpenMenu(openMenu === m.name ? null : m.name)}
            style={openMenu === m.name ? { background: "#2c2c2c", color: "#fff" } : undefined}
          >
            {m.name}
          </span>
          {openMenu === m.name && (
            <div className="menu-drop">
              {m.items.map((item, i) =>
                item.divider ? (
                  <div key={i} className="menu-divider" />
                ) : (
                  <div
                    key={i}
                    className={`menu-item${item.disabled ? " disabled" : ""}`}
                    onClick={() => click(item)}
                  >
                    {item.label}
                  </div>
                )
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
