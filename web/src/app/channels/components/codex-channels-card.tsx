"use client";

import { useState } from "react";
import { Edit3, Image as ImageIcon, LoaderCircle, Plus, Save, ShieldCheck, Trash2, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { testCodexChannel, type CodexChannel } from "@/lib/api";

import { useSettingsStore } from "../../settings/store";

const systemName = "系统渠道";
const testPrompt = "生成一只鸡";
const typeLabels: Record<CodexChannel["type"], string> = { system: "系统", tool_call: "工具调用" };

export function CodexChannelsCard() {
  const [editingId, setEditingId] = useState<string | null>(null);
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const addCodexChannel = useSettingsStore((state) => state.addCodexChannel);
  const updateCodexChannel = useSettingsStore((state) => state.updateCodexChannel);
  const deleteCodexChannel = useSettingsStore((state) => state.deleteCodexChannel);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  if (isLoadingConfig || !config?.codex_channels) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  const channels = config.codex_channels.channels || [];
  const editing = channels.find((channel) => channel.id === editingId) || null;

  const handleAdd = () => {
    addCodexChannel();
    window.setTimeout(() => {
      const latest = useSettingsStore.getState().config?.codex_channels?.channels || [];
      setEditingId(latest[latest.length - 1]?.id || null);
    }, 0);
  };

  return (
    <>
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-5 p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-base font-semibold text-stone-900">
                <Workflow className="size-5 text-stone-500" />
                Codex 渠道
              </div>
              <p className="mt-1 text-xs leading-6 text-stone-500">
                权重越高命中概率越高，0 表示不参与；每个渠道只维护一个映射模型。
              </p>
              <p className="mt-2 max-w-none overflow-x-auto whitespace-nowrap rounded-xl border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs leading-6 text-amber-800">
                type=system 走本系统逆向，type=tool_call 走第三方中转站工具调用。
              </p>
            </div>
            <Button type="button" variant="outline" className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700" onClick={handleAdd}>
              <Plus className="size-4" />
              添加渠道
            </Button>
          </div>

          <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>渠道</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>权重</TableHead>
                  <TableHead>上游</TableHead>
                  <TableHead>模型映射</TableHead>
                  <TableHead className="w-32 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {channels.map((channel) => {
                  const isSystem = channel.type === "system";
                  const enabled = isSystem || Boolean(channel.enabled);
                  return (
                    <TableRow key={channel.id}>
                      <TableCell>
                        <div className="flex min-w-0 items-center gap-2">
                          {isSystem ? <ShieldCheck className="size-4 shrink-0 text-emerald-600" /> : null}
                          <span className="truncate font-medium text-stone-900">{isSystem ? systemName : channel.name || "未命名渠道"}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{typeLabels[channel.type] || channel.type}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={enabled ? "success" : "outline"}>{enabled ? "启用" : "停用"}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-sm">{channel.weight ?? 1}</TableCell>
                      <TableCell className="font-mono text-xs text-stone-600">{isSystem ? "-" : channel.upstream_model || "-"}</TableCell>
                      <TableCell className="font-mono text-xs text-stone-600">{isSystem ? "-" : channel.mapped_model || channel.mapped_models?.[0] || "-"}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-2">
                          <Button type="button" variant="outline" size="icon" className="size-8 rounded-lg border-stone-200 bg-white" onClick={() => setEditingId(channel.id)} title="编辑渠道">
                            <Edit3 className="size-4" />
                          </Button>
                          {!isSystem ? (
                            <Button type="button" variant="outline" size="icon" className="size-8 rounded-lg border-rose-200 bg-white text-rose-700 hover:bg-rose-50" onClick={() => deleteCodexChannel(channel.id)} title="删除渠道">
                              <Trash2 className="size-4" />
                            </Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          <div className="flex justify-end">
            <Button className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800" onClick={() => void saveConfig()} disabled={isSavingConfig}>
              {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
              保存
            </Button>
          </div>
        </CardContent>
      </Card>
      <ChannelDialog
        key={editing?.id || "empty"}
        channel={editing}
        open={Boolean(editing)}
        onOpenChange={(open) => setEditingId(open ? editingId : null)}
        onChange={(updates) => editing && updateCodexChannel(editing.id, updates)}
      />
    </>
  );
}

function ChannelDialog({
  channel,
  open,
  onOpenChange,
  onChange,
}: {
  channel: CodexChannel | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChange: (updates: Partial<CodexChannel>) => void;
}) {
  const [testing, setTesting] = useState(false);
  const [testImage, setTestImage] = useState("");
  const [testError, setTestError] = useState("");
  if (!channel) return null;
  const isSystem = channel.type === "system";
  const mappedModel = String(channel.mapped_model || channel.mapped_models?.[0] || "");
  const runTest = async () => {
    setTesting(true);
    setTestImage("");
    setTestError("");
    try {
      const data = await testCodexChannel({ type: channel.type, base_url: channel.base_url || "", api_key: channel.api_key || "", upstream_model: channel.upstream_model || "gpt-5.5", prompt: testPrompt });
      setTestImage(data.result.image);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isSystem ? systemName : "编辑渠道"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm text-stone-700">渠道名称</label>
              <Input value={isSystem ? systemName : channel.name} disabled={isSystem} onChange={(event) => onChange({ name: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">权重</label>
              <Input type="number" min="0" value={String(channel.weight ?? 1)} onChange={(event) => onChange({ weight: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" />
            </div>
          </div>
          {!isSystem ? (
            <>
              <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
                <Checkbox checked={Boolean(channel.enabled)} onCheckedChange={(checked) => onChange({ enabled: Boolean(checked) })} />
                启用渠道
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">Base URL</label>
                  <Input value={channel.base_url || ""} onChange={(event) => onChange({ base_url: event.target.value })} placeholder="https://api.example.com/v1" className="h-10 rounded-xl border-stone-200 bg-white" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">API Key</label>
                  <Input type="password" value={channel.api_key || ""} onChange={(event) => onChange({ api_key: event.target.value })} placeholder="sk-..." className="h-10 rounded-xl border-stone-200 bg-white" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">上游模型</label>
                  <Input value={String(channel.upstream_model || "")} onChange={(event) => onChange({ upstream_model: event.target.value })} placeholder="gpt-5.5" className="h-10 rounded-xl border-stone-200 bg-white font-mono text-xs" />
                </div>
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs leading-6 text-amber-800">
                工具调用渠道会请求第三方中转站的 /v1/responses。
              </div>
            </>
          ) : null}
          {!isSystem ? (
            <div className="space-y-2">
              <label className="text-sm text-stone-700">映射模型</label>
              <Input value={mappedModel} onChange={(event) => onChange({ mapped_model: event.target.value, mapped_models: [event.target.value] })} placeholder="gpt-image-2" className="h-10 rounded-xl border-stone-200 bg-white font-mono text-xs" />
            </div>
          ) : null}
          {!isSystem ? (
            <div className="space-y-3 rounded-xl border border-stone-200 bg-stone-50/70 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-stone-900">测试生图</div>
                  <div className="mt-1 text-xs text-stone-500">提示词：{testPrompt} · 1024x1024</div>
                </div>
                <Button type="button" variant="outline" className="h-9 rounded-lg border-stone-200 bg-white px-3 text-stone-700" onClick={() => void runTest()} disabled={testing || !String(channel.base_url || "").trim() || !String(channel.api_key || "").trim()}>
                  {testing ? <LoaderCircle className="size-4 animate-spin" /> : <ImageIcon className="size-4" />}
                  开始测试
                </Button>
              </div>
              {testing ? <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">生成中，请等待...</div> : null}
              {testError ? <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{testError}</div> : null}
              {testImage ? <img src={`data:image/png;base64,${testImage}`} alt="测试结果" className="max-h-80 rounded-lg border border-stone-200 bg-white object-contain" /> : null}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" className="rounded-lg bg-stone-950 text-white hover:bg-stone-800" onClick={() => onOpenChange(false)}>
            完成
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
