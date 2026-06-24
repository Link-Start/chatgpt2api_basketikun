"use client";

import { create } from "zustand";
import { toast } from "sonner";

import {
  createCPAPool,
  deleteCPAPool,
  fetchCPAPoolFiles,
  fetchCPAPools,
  fetchRegisterConfig,
  resetRegister as resetRegisterApi,
  resetOutlookPool as resetOutlookPoolApi,
  fetchSettingsConfig,
  syncImageStorage,
  startRegister,
  startCPAImport,
  stopRegister,
  testImageStorageConnection,
  updateCPAPool,
  updateRegisterConfig,
  updateSettingsConfig,
  type CodexChannel,
  type CodexChannelsSettings,
  type CPAPool,
  type CPARemoteFile,
  type ImageStorageMode,
  type ImageStorageSettings,
  type ProxyRuntimeClearanceMode,
  type ProxyRuntimeEgressMode,
  type ProxyRuntimeSettings,
  type RegisterConfig,
  type SettingsConfig,
  type ThirdPartyAppsSettings,
} from "@/lib/api";

export const PAGE_SIZE_OPTIONS = ["50", "100", "200"] as const;

export type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];

const DEFAULT_PROXY_RUNTIME: ProxyRuntimeSettings = {
  enabled: false,
  egress_mode: "direct",
  proxy_url: "",
  resource_proxy_url: "",
  skip_ssl_verify: false,
  reset_session_status_codes: [403],
  clearance: {
    enabled: false,
    mode: "none",
    cf_cookies: "",
    cf_clearance: "",
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    browser: "chrome",
    flaresolverr_url: "",
    timeout_sec: 60,
    refresh_interval: 3600,
    warm_up_on_start: false,
    has_cf_cookies: false,
    has_cf_clearance: false,
  },
};

const DEFAULT_THIRD_PARTY_APPS: ThirdPartyAppsSettings = {
  infinite_canvas: {
    enabled: false,
    url: "https://canvas.best",
  },
};

const DEFAULT_CODEX_CHANNELS: CodexChannelsSettings = {
  channels: [],
};

const CODEX_SYSTEM_MODEL = "gpt-image-2";
const CODEX_CHANNEL_TYPES = new Set(["system", "tool_call"]);

function normalizeCodexChannelType(channel: Partial<CodexChannel> & { system?: boolean }) {
  if (channel.system || channel.id === "system") return "system";
  const type = String(channel.type || "").trim().toLowerCase();
  if (CODEX_CHANNEL_TYPES.has(type)) return type as CodexChannel["type"];
  return "tool_call";
}

function normalizeProxyRuntime(value: unknown): ProxyRuntimeSettings {
  const source = typeof value === "object" && value !== null ? value as Partial<ProxyRuntimeSettings> : {};
  const clearanceSource = typeof source.clearance === "object" && source.clearance !== null
    ? source.clearance as Partial<ProxyRuntimeSettings["clearance"]>
    : {};
  const egressMode = source.egress_mode === "single_proxy" ? "single_proxy" : "direct";
  const clearanceMode: ProxyRuntimeClearanceMode = clearanceSource.mode === "manual" || clearanceSource.mode === "flaresolverr"
    ? clearanceSource.mode
    : "none";
  const statusCodes = Array.isArray(source.reset_session_status_codes)
    ? source.reset_session_status_codes
      .map((item) => Number(item))
      .filter((item) => Number.isInteger(item) && item >= 100 && item <= 599)
    : [];
  return {
    ...DEFAULT_PROXY_RUNTIME,
    ...source,
    enabled: Boolean(source.enabled),
    egress_mode: egressMode as ProxyRuntimeEgressMode,
    proxy_url: String(source.proxy_url || ""),
    resource_proxy_url: String(source.resource_proxy_url || ""),
    skip_ssl_verify: Boolean(source.skip_ssl_verify),
    reset_session_status_codes: statusCodes.length > 0 ? statusCodes : [403],
    clearance: {
      ...DEFAULT_PROXY_RUNTIME.clearance,
      ...clearanceSource,
      enabled: Boolean(clearanceSource.enabled),
      mode: clearanceMode,
      cf_cookies: String(clearanceSource.cf_cookies || ""),
      cf_clearance: String(clearanceSource.cf_clearance || ""),
      user_agent: String(clearanceSource.user_agent || DEFAULT_PROXY_RUNTIME.clearance.user_agent),
      browser: String(clearanceSource.browser || "chrome"),
      flaresolverr_url: String(clearanceSource.flaresolverr_url || ""),
      timeout_sec: Number(clearanceSource.timeout_sec || 60),
      refresh_interval: Number(clearanceSource.refresh_interval || 3600),
      warm_up_on_start: Boolean(clearanceSource.warm_up_on_start),
      has_cf_cookies: Boolean(clearanceSource.has_cf_cookies),
      has_cf_clearance: Boolean(clearanceSource.has_cf_clearance),
    },
  };
}

function normalizeThirdPartyApps(value: unknown): ThirdPartyAppsSettings {
  const source = typeof value === "object" && value !== null ? value as Partial<ThirdPartyAppsSettings> : {};
  const canvas = typeof source.infinite_canvas === "object" && source.infinite_canvas
    ? source.infinite_canvas
    : {};
  return {
    infinite_canvas: {
      enabled: Boolean(canvas.enabled),
      url: String(canvas.url || DEFAULT_THIRD_PARTY_APPS.infinite_canvas.url),
    },
  };
}

function normalizeMappedModel(channel: Partial<CodexChannel>) {
  return String(channel.mapped_model || channel.mapped_models?.[0] || "").trim();
}

function normalizeCodexChannels(value: unknown): CodexChannelsSettings {
  const source = typeof value === "object" && value !== null ? value as Partial<CodexChannelsSettings> : {};
  const channels = Array.isArray(source.channels) ? source.channels : [];
  const system = channels.find((item) => typeof item === "object" && item !== null && normalizeCodexChannelType(item as Partial<CodexChannel> & { system?: boolean }) === "system") as Partial<CodexChannel> | undefined;
  return {
    channels: [
      {
        id: "system",
        type: "system",
        enabled: true,
        name: "系统渠道",
        base_url: "",
        api_key: "",
        upstream_model: "gpt-5.5",
        weight: Number(system?.weight ?? 1),
        mapped_models: [CODEX_SYSTEM_MODEL],
        model_prefix: "",
        mapped_model: CODEX_SYSTEM_MODEL,
      },
      ...channels.filter((item) => !(typeof item === "object" && item !== null && normalizeCodexChannelType(item as Partial<CodexChannel> & { system?: boolean }) === "system")).map((item, index) => {
      const channel = typeof item === "object" && item !== null ? item as Partial<CodexChannel> : {};
      const prefix = String(channel.model_prefix || "").trim().toLowerCase();
      const upstreamModel = String(channel.upstream_model || "gpt-5.5").trim() || "gpt-5.5";
      const mappedModel = normalizeMappedModel(channel) || (prefix ? `${prefix}-gpt-image-2` : "gpt-image-2");
      return {
        id: String(channel.id || `channel-${index + 1}`),
        type: normalizeCodexChannelType(channel),
        enabled: Boolean(channel.enabled),
        name: String(channel.name || ""),
        base_url: String(channel.base_url || ""),
        api_key: String(channel.api_key || ""),
        upstream_model: upstreamModel,
        weight: Number(channel.weight ?? 1),
        mapped_models: [mappedModel],
        model_prefix: prefix,
        mapped_model: mappedModel,
      };
    })],
  };
}

function normalizeConfig(config: SettingsConfig): SettingsConfig {
  const imageStorage = typeof config.image_storage === "object" && config.image_storage
    ? config.image_storage as ImageStorageSettings
    : {
      enabled: false,
      mode: "local",
      webdav_url: "",
      webdav_username: "",
      webdav_password: "",
      webdav_root_path: "chatgpt2api/images",
      public_base_url: "",
    };
  const imageStorageMode: ImageStorageMode = imageStorage.enabled && imageStorage.mode === "both"
    ? "both"
    : imageStorage.enabled && imageStorage.mode === "webdav"
      ? "webdav"
      : "local";
  return {
    ...config,
    refresh_account_interval_seconds: Number(config.refresh_account_interval_seconds || 300),
    image_retention_days: Number(config.image_retention_days || 30),
    image_poll_timeout_secs: Number(config.image_poll_timeout_secs || 120),
    image_account_concurrency: Number(config.image_account_concurrency || 3),
    image_settle_enabled: Boolean(config.image_settle_enabled !== false),
    image_check_before_hit_enabled: Boolean(config.image_check_before_hit_enabled !== false),
    image_settle_secs: Number(config.image_settle_secs || 2.0),
    image_timeout_retry_secs: Number(config.image_timeout_retry_secs || 30),
    auto_remove_invalid_accounts: Boolean(config.auto_remove_invalid_accounts),
    auto_remove_rate_limited_accounts: Boolean(config.auto_remove_rate_limited_accounts),
    log_levels: Array.isArray(config.log_levels) ? config.log_levels : [],
    proxy: typeof config.proxy === "string" ? config.proxy : "",
    base_url: typeof config.base_url === "string" ? config.base_url : "",
    global_system_prompt: String(config.global_system_prompt || ""),
    ai_review: {
      enabled: Boolean(config.ai_review?.enabled),
      base_url: String(config.ai_review?.base_url || ""),
      api_key: String(config.ai_review?.api_key || ""),
      model: String(config.ai_review?.model || ""),
      prompt: String(config.ai_review?.prompt || ""),
    },
    image_storage: {
      enabled: Boolean(imageStorage.enabled),
      mode: imageStorageMode,
      webdav_url: String(imageStorage.webdav_url || ""),
      webdav_username: String(imageStorage.webdav_username || ""),
      webdav_password: String(imageStorage.webdav_password || ""),
      webdav_root_path: String(imageStorage.webdav_root_path || "chatgpt2api/images"),
      public_base_url: String(imageStorage.public_base_url || ""),
    },
    proxy_runtime: normalizeProxyRuntime(config.proxy_runtime),
    third_party_apps: normalizeThirdPartyApps(config.third_party_apps),
    codex_channels: normalizeCodexChannels(config.codex_channels),
  };
}

function normalizeFiles(items: CPARemoteFile[]) {
  const seen = new Set<string>();
  const files: CPARemoteFile[] = [];
  for (const item of items) {
    const name = String(item.name || "").trim();
    if (!name || seen.has(name)) {
      continue;
    }
    seen.add(name);
    files.push({
      name,
      email: String(item.email || "").trim(),
    });
  }
  return files;
}

type SettingsStore = {
  config: SettingsConfig | null;
  isLoadingConfig: boolean;
  isSavingConfig: boolean;
  isTestingImageStorage: boolean;
  isSyncingImageStorage: boolean;

  registerConfig: RegisterConfig | null;
  isLoadingRegister: boolean;
  isSavingRegister: boolean;

  pools: CPAPool[];
  isLoadingPools: boolean;
  deletingId: string | null;
  loadingFilesId: string | null;

  dialogOpen: boolean;
  editingPool: CPAPool | null;
  formName: string;
  formBaseUrl: string;
  formSecretKey: string;
  showSecret: boolean;
  isSavingPool: boolean;

  browserOpen: boolean;
  browserPool: CPAPool | null;
  remoteFiles: CPARemoteFile[];
  selectedNames: string[];
  fileQuery: string;
  filePage: number;
  pageSize: PageSizeOption;
  isStartingImport: boolean;

  initialize: () => Promise<void>;
  loadConfig: () => Promise<void>;
  saveConfig: () => Promise<boolean>;
  setRefreshAccountIntervalSeconds: (value: string) => void;
  setImageRetentionDays: (value: string) => void;
  setImagePollTimeoutSecs: (value: string) => void;
  setImageAccountConcurrency: (value: string) => void;
  setImageSettleEnabled: (value: boolean) => void;
  setImageCheckBeforeHitEnabled: (value: boolean) => void;
  setImageSettleSecs: (value: string) => void;
  setImageTimeoutRetrySecs: (value: string) => void;
  setAutoRemoveInvalidAccounts: (value: boolean) => void;
  setAutoRemoveRateLimitedAccounts: (value: boolean) => void;
  setLogLevel: (level: string, enabled: boolean) => void;
  setProxy: (value: string) => void;
  setBaseUrl: (value: string) => void;
  setGlobalSystemPrompt: (value: string) => void;
  setAIReviewField: (key: "enabled" | "base_url" | "api_key" | "model" | "prompt", value: string | boolean) => void;
  setImageStorageField: (key: keyof ImageStorageSettings, value: string | boolean) => void;
  setProxyRuntimeField: <K extends keyof ProxyRuntimeSettings>(key: K, value: ProxyRuntimeSettings[K]) => void;
  setProxyRuntimeClearanceField: <K extends keyof ProxyRuntimeSettings["clearance"]>(key: K, value: ProxyRuntimeSettings["clearance"][K]) => void;
  setProxyRuntimeStatusCodesText: (value: string) => void;
  setInfiniteCanvasField: <K extends keyof ThirdPartyAppsSettings["infinite_canvas"]>(key: K, value: ThirdPartyAppsSettings["infinite_canvas"][K]) => void;
  addCodexChannel: () => void;
  updateCodexChannel: (id: string, updates: Partial<CodexChannel>) => void;
  deleteCodexChannel: (id: string) => void;
  testImageStorage: () => Promise<void>;
  syncImagesToWebDAV: () => Promise<void>;

  loadRegister: (silent?: boolean) => Promise<void>;
  setRegisterConfig: (config: RegisterConfig) => void;
  setRegisterProxy: (value: string) => void;
  setRegisterTotal: (value: string) => void;
  setRegisterThreads: (value: string) => void;
  setRegisterMode: (value: "total" | "quota" | "available") => void;
  setRegisterTargetQuota: (value: string) => void;
  setRegisterTargetAvailable: (value: string) => void;
  setRegisterCheckInterval: (value: string) => void;
  setRegisterMailField: (key: "request_timeout" | "wait_timeout" | "wait_interval", value: string) => void;
  addRegisterProvider: () => void;
  updateRegisterProvider: (index: number, updates: Record<string, unknown>) => void;
  deleteRegisterProvider: (index: number) => void;
  saveRegister: () => Promise<void>;
  toggleRegister: () => Promise<void>;
  resetRegister: () => Promise<void>;
  resetOutlookPool: (scope: "all" | "failed" | "unused") => Promise<void>;

  loadPools: (silent?: boolean) => Promise<void>;
  openAddDialog: () => void;
  openEditDialog: (pool: CPAPool) => void;
  setDialogOpen: (open: boolean) => void;
  setFormName: (value: string) => void;
  setFormBaseUrl: (value: string) => void;
  setFormSecretKey: (value: string) => void;
  setShowSecret: (checked: boolean) => void;
  savePool: () => Promise<void>;
  deletePool: (pool: CPAPool) => Promise<void>;

  browseFiles: (pool: CPAPool) => Promise<void>;
  setBrowserOpen: (open: boolean) => void;
  toggleFile: (name: string, checked: boolean) => void;
  replaceSelectedNames: (names: string[]) => void;
  setFileQuery: (value: string) => void;
  setFilePage: (page: number) => void;
  setPageSize: (value: PageSizeOption) => void;
  startImport: () => Promise<void>;
};

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  config: null,
  isLoadingConfig: true,
  isSavingConfig: false,
  isTestingImageStorage: false,
  isSyncingImageStorage: false,

  registerConfig: null,
  isLoadingRegister: true,
  isSavingRegister: false,

  pools: [],
  isLoadingPools: true,
  deletingId: null,
  loadingFilesId: null,

  dialogOpen: false,
  editingPool: null,
  formName: "",
  formBaseUrl: "",
  formSecretKey: "",
  showSecret: false,
  isSavingPool: false,

  browserOpen: false,
  browserPool: null,
  remoteFiles: [],
  selectedNames: [],
  fileQuery: "",
  filePage: 1,
  pageSize: "100",
  isStartingImport: false,

  initialize: async () => {
    await Promise.allSettled([get().loadConfig(), get().loadPools()]);
  },

  loadConfig: async () => {
    set({ isLoadingConfig: true });
    try {
      const data = await fetchSettingsConfig();
      const normalized = normalizeConfig(data.config);
      set({
        config: normalized,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载系统配置失败");
    } finally {
      set({ isLoadingConfig: false });
    }
  },

  saveConfig: async () => {
    const { config } = get();
    if (!config) {
      return false;
    }

    set({ isSavingConfig: true });
    try {
      const data = await updateSettingsConfig({
        ...config,
        refresh_account_interval_seconds: Math.max(1, Number(config.refresh_account_interval_seconds) || 300),
        image_retention_days: Math.max(1, Number(config.image_retention_days) || 30),
        image_poll_timeout_secs: Math.max(1, Number(config.image_poll_timeout_secs) || 120),
        image_account_concurrency: Math.max(1, Number(config.image_account_concurrency) || 3),
        image_settle_enabled: Boolean(config.image_settle_enabled !== false),
        image_check_before_hit_enabled: Boolean(config.image_check_before_hit_enabled !== false),
        image_settle_secs: Math.max(0.5, Number(config.image_settle_secs) || 2.0),
        image_timeout_retry_secs: Math.max(1, Number(config.image_timeout_retry_secs) || 30),
        auto_remove_invalid_accounts: Boolean(config.auto_remove_invalid_accounts),
        auto_remove_rate_limited_accounts: Boolean(config.auto_remove_rate_limited_accounts),
        proxy: config.proxy.trim(),
        base_url: String(config.base_url || "").trim(),
        global_system_prompt: String(config.global_system_prompt || "").trim(),
        ai_review: {
          enabled: Boolean(config.ai_review?.enabled),
          base_url: String(config.ai_review?.base_url || "").trim(),
          api_key: String(config.ai_review?.api_key || "").trim(),
          model: String(config.ai_review?.model || "").trim(),
          prompt: String(config.ai_review?.prompt || "").trim(),
        },
        image_storage: {
          enabled: Boolean(config.image_storage?.enabled),
          mode: config.image_storage?.enabled && ["webdav", "both"].includes(String(config.image_storage?.mode)) ? config.image_storage.mode : "local",
          webdav_url: String(config.image_storage?.webdav_url || "").trim(),
          webdav_username: String(config.image_storage?.webdav_username || "").trim(),
          webdav_password: String(config.image_storage?.webdav_password || "").trim(),
          webdav_root_path: String(config.image_storage?.webdav_root_path || "chatgpt2api/images").trim(),
          public_base_url: String(config.image_storage?.public_base_url || "").trim(),
        },
        proxy_runtime: {
          ...normalizeProxyRuntime(config.proxy_runtime),
          proxy_url: String(config.proxy_runtime?.proxy_url || "").trim(),
          resource_proxy_url: String(config.proxy_runtime?.resource_proxy_url || "").trim(),
          reset_session_status_codes: normalizeProxyRuntime({
            reset_session_status_codes: (config.proxy_runtime?.reset_session_status_codes || [403])
              .map((item) => Number(item))
              .filter((item) => Number.isInteger(item) && item >= 100 && item <= 599),
          }).reset_session_status_codes,
          clearance: {
            ...normalizeProxyRuntime(config.proxy_runtime).clearance,
            cf_cookies: String(config.proxy_runtime?.clearance?.cf_cookies || "").trim(),
            cf_clearance: String(config.proxy_runtime?.clearance?.cf_clearance || "").trim(),
            user_agent: String(config.proxy_runtime?.clearance?.user_agent || DEFAULT_PROXY_RUNTIME.clearance.user_agent).trim(),
            browser: String(config.proxy_runtime?.clearance?.browser || "chrome").trim(),
            flaresolverr_url: String(config.proxy_runtime?.clearance?.flaresolverr_url || "").trim(),
            timeout_sec: Math.max(1, Number(config.proxy_runtime?.clearance?.timeout_sec) || 60),
            refresh_interval: Math.max(60, Number(config.proxy_runtime?.clearance?.refresh_interval) || 3600),
          },
        },
        third_party_apps: {
          infinite_canvas: {
            enabled: Boolean(config.third_party_apps?.infinite_canvas?.enabled),
            url: String(config.third_party_apps?.infinite_canvas?.url || DEFAULT_THIRD_PARTY_APPS.infinite_canvas.url).trim(),
          },
        },
        codex_channels: {
          channels: normalizeCodexChannels(config.codex_channels).channels.map((channel) => ({
            ...channel,
            name: String(channel.name || "").trim(),
            base_url: String(channel.base_url || "").trim(),
            api_key: String(channel.api_key || "").trim(),
            weight: Math.max(0, Number(channel.weight) || 0),
            mapped_model: channel.type === "system" ? CODEX_SYSTEM_MODEL : normalizeMappedModel(channel),
            mapped_models: [channel.type === "system" ? CODEX_SYSTEM_MODEL : normalizeMappedModel(channel)].filter(Boolean),
            model_prefix: String(channel.model_prefix || "").trim().toLowerCase(),
          })),
        },
      });
      set({
        config: normalizeConfig(data.config),
      });
      window.dispatchEvent(new Event("third-party-apps-updated"));
      toast.success("配置已保存");
      return true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存系统配置失败");
      return false;
    } finally {
      set({ isSavingConfig: false });
    }
  },

  setRefreshAccountIntervalSeconds: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          refresh_account_interval_seconds: value,
        },
      };
    });
  },

  setImageRetentionDays: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_retention_days: value } } : {});
  },

  setImagePollTimeoutSecs: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_poll_timeout_secs: value } } : {});
  },

  setImageAccountConcurrency: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_account_concurrency: value } } : {});
  },

  setImageSettleEnabled: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_settle_enabled: value, image_check_before_hit_enabled: value } } : {});
  },

  setImageCheckBeforeHitEnabled: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_check_before_hit_enabled: value } } : {});
  },

  setImageSettleSecs: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_settle_secs: value } } : {});
  },

  setImageTimeoutRetrySecs: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_timeout_retry_secs: value } } : {});
  },

  setAutoRemoveInvalidAccounts: (value) => {
    set((state) => state.config ? { config: { ...state.config, auto_remove_invalid_accounts: value } } : {});
  },

  setAutoRemoveRateLimitedAccounts: (value) => {
    set((state) => state.config ? { config: { ...state.config, auto_remove_rate_limited_accounts: value } } : {});
  },

  setLogLevel: (level, enabled) => {
    set((state) => {
      if (!state.config) return {};
      const levels = new Set(state.config.log_levels || []);
      if (enabled) levels.add(level);
      else levels.delete(level);
      return { config: { ...state.config, log_levels: Array.from(levels) } };
    });
  },

  setProxy: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          proxy: value,
        },
      };
    });
  },

  setBaseUrl: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          base_url: value,
        },
      };
    });
  },

  setGlobalSystemPrompt: (value) => {
    set((state) => state.config ? { config: { ...state.config, global_system_prompt: value } } : {});
  },

  setAIReviewField: (key, value) => {
    set((state) => state.config ? { config: { ...state.config, ai_review: { ...(state.config.ai_review || {}), [key]: value } } } : {});
  },

  setImageStorageField: (key, value) => {
    set((state) => {
      if (!state.config?.image_storage) {
        return {};
      }
      const next = {
        ...state.config.image_storage,
        [key]: value,
      };
      if (key === "enabled" && !value) {
        next.mode = "local";
      }
      if (key === "enabled" && value && next.mode === "local") {
        next.mode = "webdav";
      }
      return {
        config: {
          ...state.config,
          image_storage: next,
        },
      };
    });
  },

  setProxyRuntimeField: (key, value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      const runtime = normalizeProxyRuntime(state.config.proxy_runtime);
      const nextRuntime = normalizeProxyRuntime({
        ...runtime,
        [key]: value,
      });
      return {
        config: {
          ...state.config,
          proxy_runtime: nextRuntime,
        },
      };
    });
  },

  setProxyRuntimeClearanceField: (key, value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      const runtime = normalizeProxyRuntime(state.config.proxy_runtime);
      const nextRuntime = normalizeProxyRuntime({
        ...runtime,
        clearance: {
          ...runtime.clearance,
          [key]: value,
        },
      });
      return {
        config: {
          ...state.config,
          proxy_runtime: nextRuntime,
        },
      };
    });
  },

  setProxyRuntimeStatusCodesText: (value) => {
    const codes = value
      .split(/[,\s]+/)
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isInteger(item) && item >= 100 && item <= 599);
    set((state) => {
      if (!state.config) {
        return {};
      }
      const runtime = normalizeProxyRuntime(state.config.proxy_runtime);
      return {
        config: {
          ...state.config,
          proxy_runtime: normalizeProxyRuntime({
            ...runtime,
            reset_session_status_codes: codes.length > 0 ? codes : [403],
          }),
        },
      };
    });
  },

  setInfiniteCanvasField: (key, value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      const apps = normalizeThirdPartyApps(state.config.third_party_apps);
      return {
        config: {
          ...state.config,
          third_party_apps: {
            ...apps,
            infinite_canvas: {
              ...apps.infinite_canvas,
              [key]: value,
            },
          },
        },
      };
    });
  },

  addCodexChannel: () => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      const settings = normalizeCodexChannels(state.config.codex_channels || DEFAULT_CODEX_CHANNELS);
      const id = `channel-${Date.now()}`;
      return {
        config: {
          ...state.config,
          codex_channels: {
            channels: [
              ...settings.channels,
              {
                id,
                type: "tool_call",
                enabled: true,
                name: "",
                base_url: "",
                api_key: "",
                upstream_model: "gpt-5.5",
                weight: 1,
                mapped_models: ["gpt-image-2"],
                model_prefix: "",
                mapped_model: "gpt-image-2",
              },
            ],
          },
        },
      };
    });
  },

  updateCodexChannel: (id, updates) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      const settings = normalizeCodexChannels(state.config.codex_channels || DEFAULT_CODEX_CHANNELS);
      return {
        config: {
          ...state.config,
          codex_channels: {
            channels: settings.channels.map((channel) => {
              if (channel.id !== id) {
                return channel;
              }
              const next = { ...channel, ...updates };
              const prefix = String(next.model_prefix || "").trim().toLowerCase();
              const mappedModel = next.type === "system" ? CODEX_SYSTEM_MODEL : normalizeMappedModel(next);
              return {
                ...next,
                model_prefix: prefix,
                mapped_models: [mappedModel].filter(Boolean),
                mapped_model: mappedModel,
              };
            }),
          },
        },
      };
    });
  },

  deleteCodexChannel: (id) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      const settings = normalizeCodexChannels(state.config.codex_channels || DEFAULT_CODEX_CHANNELS);
      return {
        config: {
          ...state.config,
          codex_channels: {
            channels: settings.channels.filter((channel) => channel.type === "system" || channel.id !== id),
          },
        },
      };
    });
  },

  testImageStorage: async () => {
    set({ isTestingImageStorage: true });
    try {
      const saved = await get().saveConfig();
      if (!saved) {
        return;
      }
      const data = await testImageStorageConnection();
      if (data.result.ok) {
        toast.success(`WebDAV 连接可用：HTTP ${data.result.status}`);
      } else {
        toast.error(`WebDAV 连接失败：${data.result.error ?? `HTTP ${data.result.status}`}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "测试 WebDAV 失败");
    } finally {
      set({ isTestingImageStorage: false });
    }
  },

  syncImagesToWebDAV: async () => {
    set({ isSyncingImageStorage: true });
    try {
      const saved = await get().saveConfig();
      if (!saved) {
        return;
      }
      const data = await syncImageStorage();
      toast.success(`同步完成：上传 ${data.result.uploaded}，跳过 ${data.result.skipped}，失败 ${data.result.failed}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "同步图片失败");
    } finally {
      set({ isSyncingImageStorage: false });
    }
  },

  loadRegister: async (silent = false) => {
    if (!silent) set({ isLoadingRegister: true });
    try {
      const data = await fetchRegisterConfig();
      set({ registerConfig: data.register });
    } catch (error) {
      if (!silent) toast.error(error instanceof Error ? error.message : "加载注册配置失败");
    } finally {
      if (!silent) set({ isLoadingRegister: false });
    }
  },

  setRegisterConfig: (config) => {
    set({ registerConfig: config, isLoadingRegister: false });
  },

  setRegisterProxy: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, proxy: value } } : {});
  },

  setRegisterTotal: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, total: Number(value) || 0 } } : {});
  },

  setRegisterThreads: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, threads: Number(value) || 0 } } : {});
  },

  setRegisterMode: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, mode: value } } : {});
  },

  setRegisterTargetQuota: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, target_quota: Number(value) || 0 } } : {});
  },

  setRegisterTargetAvailable: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, target_available: Number(value) || 0 } } : {});
  },

  setRegisterCheckInterval: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, check_interval: Number(value) || 0 } } : {});
  },

  setRegisterMailField: (key, value) => {
    set((state) => state.registerConfig ? {
      registerConfig: {
        ...state.registerConfig,
        mail: { ...state.registerConfig.mail, [key]: Number(value) || 0 },
      },
    } : {});
  },

  addRegisterProvider: () => {
    set((state) => state.registerConfig ? {
      registerConfig: {
        ...state.registerConfig,
        mail: {
          ...state.registerConfig.mail,
          providers: [
            ...(state.registerConfig.mail.providers || []),
            { enable: true, type: "cloudmail_gen", api_base: "", admin_email: "", admin_password: "", domain: [], subdomain: [], email_prefix: "" },
          ],
        },
      },
    } : {});
  },

  updateRegisterProvider: (index, updates) => {
    set((state) => {
      if (!state.registerConfig) return {};
      const providers = [...(state.registerConfig.mail.providers || [])];
      providers[index] = { ...(providers[index] || {}), ...updates };
      return { registerConfig: { ...state.registerConfig, mail: { ...state.registerConfig.mail, providers } } };
    });
  },

  deleteRegisterProvider: (index) => {
    set((state) => state.registerConfig ? {
      registerConfig: {
        ...state.registerConfig,
        mail: {
          ...state.registerConfig.mail,
          providers: (state.registerConfig.mail.providers || []).filter((_, itemIndex) => itemIndex !== index),
        },
      },
    } : {});
  },

  saveRegister: async () => {
    const { registerConfig } = get();
    if (!registerConfig) return;
    try {
      set({ isSavingRegister: true });
      const data = await updateRegisterConfig({
        mail: registerConfig.mail,
        proxy: registerConfig.proxy.trim(),
        total: Math.max(1, Number(registerConfig.total) || 1),
        threads: Math.max(1, Number(registerConfig.threads) || 1),
        mode: registerConfig.mode,
        target_quota: Math.max(1, Number(registerConfig.target_quota) || 1),
        target_available: Math.max(1, Number(registerConfig.target_available) || 1),
        check_interval: Math.max(1, Number(registerConfig.check_interval) || 5),
      });
      set({ registerConfig: data.register });
      toast.success("注册配置已保存");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存注册配置失败");
    } finally {
      set({ isSavingRegister: false });
    }
  },

  toggleRegister: async () => {
    const { registerConfig } = get();
    if (!registerConfig) return;
    set({ isSavingRegister: true });
    try {
      if (!registerConfig.enabled) {
        await updateRegisterConfig({
          mail: registerConfig.mail,
          proxy: registerConfig.proxy.trim(),
          total: Math.max(1, Number(registerConfig.total) || 1),
          threads: Math.max(1, Number(registerConfig.threads) || 1),
          mode: registerConfig.mode,
          target_quota: Math.max(1, Number(registerConfig.target_quota) || 1),
          target_available: Math.max(1, Number(registerConfig.target_available) || 1),
          check_interval: Math.max(1, Number(registerConfig.check_interval) || 5),
        });
      }
      const data = registerConfig.enabled ? await stopRegister() : await startRegister();
      set({ registerConfig: data.register });
      toast.success(registerConfig.enabled ? "注册任务已停止" : "注册任务已启动");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "切换注册状态失败");
    } finally {
      set({ isSavingRegister: false });
    }
  },

  resetRegister: async () => {
    set({ isSavingRegister: true });
    try {
      const data = await resetRegisterApi();
      set({ registerConfig: data.register });
      toast.success("注册统计已重置");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "重置注册统计失败");
    } finally {
      set({ isSavingRegister: false });
    }
  },

  resetOutlookPool: async (scope) => {
    set({ isSavingRegister: true });
    try {
      const data = await resetOutlookPoolApi(scope);
      set({ registerConfig: data.register });
      toast.success(scope === "unused" ? "已清空未使用邮箱" : scope === "failed" ? "已清除失败/占用的邮箱状态" : "Outlook 邮箱池状态已全部重置");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "重置邮箱池状态失败");
    } finally {
      set({ isSavingRegister: false });
    }
  },

  loadPools: async (silent = false) => {
    if (!silent) {
      set({ isLoadingPools: true });
    }
    try {
      const data = await fetchCPAPools();
      set({ pools: data.pools });
    } catch (error) {
      if (!silent) {
        toast.error(error instanceof Error ? error.message : "加载 CPA 连接失败");
      }
    } finally {
      if (!silent) {
        set({ isLoadingPools: false });
      }
    }
  },

  openAddDialog: () => {
    set({
      editingPool: null,
      formName: "",
      formBaseUrl: "",
      formSecretKey: "",
      showSecret: false,
      dialogOpen: true,
    });
  },

  openEditDialog: (pool) => {
    set({
      editingPool: pool,
      formName: pool.name,
      formBaseUrl: pool.base_url,
      formSecretKey: "",
      showSecret: false,
      dialogOpen: true,
    });
  },

  setDialogOpen: (open) => {
    set({ dialogOpen: open });
  },

  setFormName: (value) => {
    set({ formName: value });
  },

  setFormBaseUrl: (value) => {
    set({ formBaseUrl: value });
  },

  setFormSecretKey: (value) => {
    set({ formSecretKey: value });
  },

  setShowSecret: (checked) => {
    set({ showSecret: checked });
  },

  savePool: async () => {
    const { editingPool, formName, formBaseUrl, formSecretKey } = get();
    if (!formBaseUrl.trim()) {
      toast.error("请输入 CPA 地址");
      return;
    }
    if (!editingPool && !formSecretKey.trim()) {
      toast.error("请输入 Secret Key");
      return;
    }

    set({ isSavingPool: true });
    try {
      if (editingPool) {
        const data = await updateCPAPool(editingPool.id, {
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          secret_key: formSecretKey.trim() || undefined,
        });
        set({ pools: data.pools, dialogOpen: false });
        toast.success("连接已更新");
      } else {
        const data = await createCPAPool({
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          secret_key: formSecretKey.trim(),
        });
        set({ pools: data.pools, dialogOpen: false });
        toast.success("连接已添加");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      set({ isSavingPool: false });
    }
  },

  deletePool: async (pool) => {
    set({ deletingId: pool.id });
    try {
      const data = await deleteCPAPool(pool.id);
      set({ pools: data.pools });
      toast.success("连接已删除");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    } finally {
      set({ deletingId: null });
    }
  },

  browseFiles: async (pool) => {
    set({ loadingFilesId: pool.id });
    try {
      const data = await fetchCPAPoolFiles(pool.id);
      const files = normalizeFiles(data.files);
      set({
        browserPool: pool,
        remoteFiles: files,
        selectedNames: [],
        fileQuery: "",
        filePage: 1,
        browserOpen: true,
      });
      toast.success(`读取成功，共 ${files.length} 个远程账号`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "读取远程账号失败");
    } finally {
      set({ loadingFilesId: null });
    }
  },

  setBrowserOpen: (open) => {
    set({ browserOpen: open });
  },

  toggleFile: (name, checked) => {
    set((state) => {
      if (checked) {
        return {
          selectedNames: Array.from(new Set([...state.selectedNames, name])),
        };
      }
      return {
        selectedNames: state.selectedNames.filter((item) => item !== name),
      };
    });
  },

  replaceSelectedNames: (names) => {
    set({ selectedNames: Array.from(new Set(names)) });
  },

  setFileQuery: (value) => {
    set({ fileQuery: value, filePage: 1 });
  },

  setFilePage: (page) => {
    set({ filePage: page });
  },

  setPageSize: (value) => {
    set({ pageSize: value, filePage: 1 });
  },

  startImport: async () => {
    const { browserPool, selectedNames, pools } = get();
    if (!browserPool) {
      return;
    }
    if (selectedNames.length === 0) {
      toast.error("请先选择要导入的账号");
      return;
    }

    set({ isStartingImport: true });
    try {
      const result = await startCPAImport(browserPool.id, selectedNames);
      set({
        pools: pools.map((pool) =>
          pool.id === browserPool.id ? { ...pool, import_job: result.import_job } : pool,
        ),
        browserOpen: false,
      });
      toast.success("导入任务已启动");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "启动导入失败");
    } finally {
      set({ isStartingImport: false });
    }
  },
}));
