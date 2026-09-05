import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import {
  getApiBase,
  setApiBase as persistApiBase,
  getConfig,
  getListings,
  clearListings as apiClearListings,
  getScanStatus,
  startScan as apiStartScan,
  stopScan as apiStopScan,
} from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

const AppStateContext = createContext(null);

const POLL_INTERVAL_MS = 15000;

export function AppStateProvider({ children }) {
  const [apiBase, setApiBaseState] = useState("");
  const [apiReady, setApiReady] = useState(false);
  const [connectionError, setConnectionError] = useState(null);

  const [config, setConfig] = useState(null);
  const [listings, setListings] = useState([]);
  const [newCount, setNewCount] = useState(0);
  const [totalValue, setTotalValue] = useState(0);
  const [scanActive, setScanActive] = useState(false);
  const [loading, setLoading] = useState(false);

  const previousNewCount = useRef(0);
  const hasPolledOnce = useRef(false);
  const pollRef = useRef(null);

  useEffect(() => {
    (async () => {
      const base = await getApiBase();
      setApiBaseState(base);
      setApiReady(true);
      if (Platform.OS === "android") {
        Notifications.setNotificationChannelAsync("default", {
          name: "Yeni İlan Bildirimleri",
          importance: Notifications.AndroidImportance.HIGH,
          vibrationPattern: [0, 250, 250, 250],
        }).catch(() => {});
      }
      Notifications.requestPermissionsAsync().catch(() => {});
    })();
  }, []);

  const updateApiBase = useCallback(async (url) => {
    await persistApiBase(url);
    setApiBaseState(url.trim().replace(/\/+$/, ""));
    setConnectionError(null);
  }, []);

  const refreshConfig = useCallback(async () => {
    if (!apiBase) return;
    try {
      const cfg = await getConfig();
      setConfig(cfg);
      setConnectionError(null);
    } catch (e) {
      setConnectionError(e.message);
    }
  }, [apiBase]);

  const refreshListings = useCallback(async () => {
    if (!apiBase) return;
    try {
      const data = await getListings();
      setListings(data.listings);
      setTotalValue(data.listings.reduce((sum, row) => sum + (Number(row.price) || 0), 0));

      if (hasPolledOnce.current && data.new_count > previousNewCount.current) {
        const diff = data.new_count - previousNewCount.current;
        Notifications.scheduleNotificationAsync({
          content: {
            title: "🎯 Yeni ilan bulundu!",
            body: `${diff} yeni araç ilanı kriterlerinize uyuyor.`,
          },
          trigger: null,
        }).catch(() => {});
      }
      previousNewCount.current = data.new_count;
      hasPolledOnce.current = true;
      setNewCount(data.new_count);
      setConnectionError(null);
    } catch (e) {
      setConnectionError(e.message);
    }
  }, [apiBase]);

  const refreshStatus = useCallback(async () => {
    if (!apiBase) return;
    try {
      const status = await getScanStatus();
      setScanActive(status.active);
      setConnectionError(null);
    } catch (e) {
      setConnectionError(e.message);
    }
  }, [apiBase]);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshConfig(), refreshListings(), refreshStatus()]);
  }, [refreshConfig, refreshListings, refreshStatus]);

  useEffect(() => {
    if (apiBase) refreshAll();
  }, [apiBase]);

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (scanActive && apiBase) {
      pollRef.current = setInterval(() => {
        refreshListings();
        refreshStatus();
      }, POLL_INTERVAL_MS);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [scanActive, apiBase, refreshListings, refreshStatus]);

  const startScan = useCallback(
    async (criteria) => {
      setLoading(true);
      try {
        await apiStartScan(criteria);
        setScanActive(true);
        await refreshListings();
      } finally {
        setLoading(false);
      }
    },
    [refreshListings]
  );

  const stopScan = useCallback(async () => {
    setLoading(true);
    try {
      await apiStopScan();
      setScanActive(false);
    } finally {
      setLoading(false);
    }
  }, []);

  const clearAll = useCallback(async () => {
    setLoading(true);
    try {
      await apiClearListings();
      await refreshListings();
    } finally {
      setLoading(false);
    }
  }, [refreshListings]);

  const value = {
    apiBase,
    apiReady,
    connectionError,
    updateApiBase,
    config,
    listings,
    newCount,
    totalValue,
    scanActive,
    loading,
    refreshAll,
    refreshListings,
    refreshStatus,
    startScan,
    stopScan,
    clearAll,
  };

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppStateProvider");
  return ctx;
}
