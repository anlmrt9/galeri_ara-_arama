import React, { useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from "react-native";
import { Picker } from "@react-native-picker/picker";
import { colors } from "../theme";
import { useAppState } from "../AppContext";

const DAMAGE_STATES = ["orijinal", "boyali", "degisen"];
const DAMAGE_STATE_LABEL = { orijinal: "Orijinal", boyali: "Boyalı", degisen: "Değişen" };
const DAMAGE_STATE_COLOR = { orijinal: colors.surface, boyali: "#1e90ff", degisen: "#ff4b4b" };

export default function FiltersScreen({ navigation }) {
  const { config, startScan, loading, apiBase } = useAppState();

  const [brand, setBrand] = useState("Tümü");
  const [model, setModel] = useState("Tümü");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [minYear, setMinYear] = useState("");
  const [maxYear, setMaxYear] = useState("");
  const [minKm, setMinKm] = useState("");
  const [maxKm, setMaxKm] = useState("");
  const [maxTramer, setMaxTramer] = useState("");
  const [duration, setDuration] = useState("24");
  const [sites, setSites] = useState(config?.sites || []);
  const [damageState, setDamageState] = useState({});

  const siteOptions = config?.sites || [];
  const catalog = config?.catalog || {};
  const damageParts = config?.damage_parts || [];
  const brandOptions = ["Tümü", ...Object.keys(catalog).sort()];
  const modelOptions = brand === "Tümü" ? ["Tümü"] : ["Tümü", ...(catalog[brand] || []).slice().sort()];

  const effectiveSites = sites.length ? sites : siteOptions;

  const toggleSite = (site) => {
    setSites((prev) => {
      const base = prev.length ? prev : siteOptions;
      return base.includes(site) ? base.filter((s) => s !== site) : [...base, site];
    });
  };

  const cycleDamage = (partId) => {
    setDamageState((prev) => {
      const current = prev[partId] || "orijinal";
      const next = DAMAGE_STATES[(DAMAGE_STATES.indexOf(current) + 1) % DAMAGE_STATES.length];
      return { ...prev, [partId]: next };
    });
  };

  const allowedParts = useMemo(() => {
    return damageParts
      .filter((p) => p.scraper_key && ["boyali", "degisen"].includes(damageState[p.id]))
      .map((p) => p.scraper_key);
  }, [damageState, damageParts]);

  const numOr = (str, fallback) => {
    const n = parseFloat(str);
    return Number.isFinite(n) ? n : fallback;
  };

  const handleSubmit = async () => {
    if (effectiveSites.length === 0) {
      Alert.alert("Site seçin", "En az bir hedef site seçmelisiniz.");
      return;
    }
    const criteria = {
      sites: effectiveSites,
      brand,
      model,
      min_price: numOr(minPrice, 0),
      max_price: numOr(maxPrice, 999999999),
      min_year: numOr(minYear, 1970),
      max_year: numOr(maxYear, 2030),
      min_km: numOr(minKm, 0),
      max_km: numOr(maxKm, 1000000),
      max_tramer: numOr(maxTramer, 999999999),
      duration_hours: numOr(duration, 24),
      allowed_parts: allowedParts,
    };
    try {
      await startScan(criteria);
      navigation.navigate("Ana Sayfa");
    } catch (e) {
      Alert.alert("Tarama başlatılamadı", e.message);
    }
  };

  if (!apiBase) {
    return (
      <View style={styles.centerWrap}>
        <Text style={styles.emptyBody}>Önce Ayarlar sekmesinden API adresini girin.</Text>
      </View>
    );
  }

  if (!config) {
    return (
      <View style={styles.centerWrap}>
        <ActivityIndicator color={colors.pink} />
        <Text style={[styles.emptyBody, { marginTop: 12 }]}>Ayarlar yükleniyor...</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 20, paddingBottom: 60 }}>
      <Text style={styles.header}>🎯 Hedef Araç Özellikleri</Text>

      <Text style={styles.label}>Marka</Text>
      <View style={styles.pickerWrap}>
        <Picker
          selectedValue={brand}
          onValueChange={(v) => {
            setBrand(v);
            setModel("Tümü");
          }}
          style={styles.picker}
          dropdownIconColor={colors.white}
        >
          {brandOptions.map((b) => (
            <Picker.Item key={b} label={b} value={b} color={colors.white} />
          ))}
        </Picker>
      </View>

      <Text style={styles.label}>Model</Text>
      <View style={styles.pickerWrap}>
        <Picker selectedValue={model} onValueChange={setModel} style={styles.picker} dropdownIconColor={colors.white}>
          {modelOptions.map((m) => (
            <Picker.Item key={m} label={m} value={m} color={colors.white} />
          ))}
        </Picker>
      </View>

      <Text style={styles.sectionLabel}>Fiyat / Yıl / Kilometre / Tramer</Text>
      <View style={styles.row}>
        <LabeledInput style={styles.flex1} label="Min. Fiyat (TL)" value={minPrice} onChangeText={setMinPrice} placeholder="Örn: 500000" />
        <LabeledInput style={styles.flex1} label="Max. Fiyat (TL)" value={maxPrice} onChangeText={setMaxPrice} placeholder="Limit yok" />
      </View>
      <View style={styles.row}>
        <LabeledInput style={styles.flex1} label="Min. Yıl" value={minYear} onChangeText={setMinYear} placeholder="Örn: 2015" />
        <LabeledInput style={styles.flex1} label="Max. Yıl" value={maxYear} onChangeText={setMaxYear} placeholder="Örn: 2024" />
      </View>
      <View style={styles.row}>
        <LabeledInput style={styles.flex1} label="Min. KM" value={minKm} onChangeText={setMinKm} placeholder="Örn: 0" />
        <LabeledInput style={styles.flex1} label="Max. KM" value={maxKm} onChangeText={setMaxKm} placeholder="Örn: 120000" />
      </View>
      <View style={styles.row}>
        <LabeledInput style={styles.flex1} label="Max. Tramer (TL)" value={maxTramer} onChangeText={setMaxTramer} placeholder="Örn: 15000" />
        <LabeledInput style={styles.flex1} label="Süre (Saat)" value={duration} onChangeText={setDuration} placeholder="24" />
      </View>

      <Text style={styles.sectionLabel}>Hedef Kanallar / Siteler</Text>
      <View style={styles.chipsWrap}>
        {siteOptions.map((site) => {
          const active = effectiveSites.includes(site);
          return (
            <TouchableOpacity
              key={site}
              onPress={() => toggleSite(site)}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{site}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <Text style={styles.sectionLabel}>🚘 Kabul Edilen Maksimum Hasar</Text>
      <Text style={styles.helperText}>
        Her parçaya dokunarak izin verdiğiniz maksimum hasar durumunu seçin (Orijinal → Boyalı → Değişen).
      </Text>
      <View style={styles.damageList}>
        {damageParts.map((part) => {
          const state = damageState[part.id] || "orijinal";
          return (
            <TouchableOpacity key={part.id} style={styles.damageRow} onPress={() => cycleDamage(part.id)}>
              <Text style={styles.damagePartLabel}>{part.label}</Text>
              <View style={[styles.damageBadge, { backgroundColor: DAMAGE_STATE_COLOR[state] }]}>
                <Text style={styles.damageBadgeText}>{DAMAGE_STATE_LABEL[state]}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      <TouchableOpacity style={styles.submitBtn} onPress={handleSubmit} disabled={loading}>
        {loading ? (
          <ActivityIndicator color={colors.white} />
        ) : (
          <Text style={styles.submitBtnText}>🚀 Tarama ve Tedarik Sürecini Başlat</Text>
        )}
      </TouchableOpacity>
    </ScrollView>
  );
}

function LabeledInput({ label, style, ...props }) {
  return (
    <View style={[styles.inputWrap, style]}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={styles.input}
        placeholderTextColor={colors.muted}
        keyboardType="numeric"
        {...props}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.navy },
  centerWrap: { flex: 1, backgroundColor: colors.navy, alignItems: "center", justifyContent: "center", padding: 32 },
  emptyBody: { color: colors.muted, fontSize: 14, textAlign: "center" },
  header: { color: colors.white, fontSize: 18, fontWeight: "600", marginBottom: 20 },
  label: { color: "#c7cae3", fontSize: 13, marginBottom: 6 },
  sectionLabel: { color: colors.white, fontSize: 15, fontWeight: "600", marginTop: 20, marginBottom: 10 },
  helperText: { color: colors.muted, fontSize: 12.5, marginBottom: 12, lineHeight: 18 },
  pickerWrap: {
    backgroundColor: colors.surface,
    borderRadius: 10,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.border,
  },
  picker: { color: colors.white },
  row: { flexDirection: "row", gap: 12 },
  flex1: { flex: 1 },
  inputWrap: { marginBottom: 14 },
  input: {
    backgroundColor: colors.surface,
    color: colors.white,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipsWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 20,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.violet, borderColor: colors.violet },
  chipText: { color: colors.muted, fontSize: 13 },
  chipTextActive: { color: colors.white, fontWeight: "600" },
  damageList: { gap: 8 },
  damageRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.surface,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.border,
  },
  damagePartLabel: { color: colors.white, fontSize: 14 },
  damageBadge: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 12 },
  damageBadgeText: { color: colors.white, fontSize: 12, fontWeight: "600" },
  submitBtn: {
    marginTop: 28,
    backgroundColor: colors.violet,
    borderRadius: 50,
    paddingVertical: 16,
    alignItems: "center",
  },
  submitBtnText: { color: colors.white, fontWeight: "700", fontSize: 15 },
});
