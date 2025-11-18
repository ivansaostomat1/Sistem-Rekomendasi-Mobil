import { Brand, SegmentInfo, FuelType, TopResaleCar } from "@/types";

// API Configuration
export const API_BASE = "http://localhost:8000";

// Budget Configuration
export const BUDGET_MIN = 150_000_000;
export const BUDGET_MAX = 2_000_000_000;
export const BUDGET_STEP = 50_000_000;

// Brand Data
export const BRANDS: Brand[] = [
  { name: "Toyota", logo: "/brands/toyota.png" },
  { name: "Honda", logo: "/brands/logohonda.png" },
  { name: "Lexus", logo: "/brands/logolexus.png" },
  { name: "BMW", logo: "/brands/logobmw.png" },
  { name: "Mercedes-Benz", logo: "/brands/logomercedes.png" },
  { name: "Suzuki", logo: "/brands/logosuzuki.png" },
  { name: "Hyundai", logo: "/brands/logohyundai.png" },
  { name: "Mazda", logo: "/brands/logomazda.png" },
  { name: "Mitsubishi", logo: "/brands/logomitsu.png" },
  { name: "Nissan", logo: "/brands/logonissan.png" },
];

// Segment Information
export const SEGMENTASI_INFO: SegmentInfo[] = [
  { 
    title: "SUV", 
    desc: "Sport Utility Vehicle — cocok untuk keluarga atau perjalanan jauh, ground clearance tinggi dan tampilan gagah." 
  },
  { 
    title: "MPV", 
    desc: "Multi Purpose Vehicle — fokus pada kenyamanan penumpang, cocok untuk keluarga besar atau mobil harian." 
  },
  { 
    title: "Sedan", 
    desc: "Tampil elegan dan nyaman di jalan raya, biasanya memiliki performa stabil dan interior mewah." 
  },
  { 
    title: "Hatchback", 
    desc: "Desain ringkas dan praktis, irit bahan bakar serta mudah dikendarai di area perkotaan." 
  },
  { 
    title: "Crossover", 
    desc: "Gabungan SUV dan Hatchback — tampilan tangguh tapi tetap nyaman dan hemat bahan bakar." 
  },
  { 
    title: "City Car", 
    desc: "Mobil berukuran sangat kompak, ideal untuk manuver dan parkir di perkotaan padat, serta hemat bahan bakar." 
  },
  { 
    title: "Convertible", 
    desc: "Mobil mewah dengan atap yang bisa dibuka (cabriolet), fokus pada gaya hidup dan pengalaman berkendara." 
  },
  { 
    title: "Coupe", 
    desc: "Mobil sporty dua pintu yang elegan dengan desain aerodinamis, mengutamakan performa dan kecepatan." 
  },
  { 
    title: "Wagon", 
    desc: "Mobil station wagon, perpaduan antara sedan dan hatchback yang memiliki ruang bagasi lebih panjang/luas." 
  },
  { 
    title: "Van", 
    desc: "Kendaraan besar untuk mengangkut banyak penumpang atau barang, sangat praktis untuk bisnis atau perjalanan rombongan." 
  },
];

// Fuel Type Data
export const FUEL_DATA: FuelType[] = [
  {
    title: "BEV (Battery Electric Vehicle)",
    desc: "Mobil listrik murni yang ditenagai oleh baterai dan motor listrik. Nol emisi, pengisian daya di rumah/stasiun umum.",
    iconKey: "bev",
  },
  {
    title: "PHEV (Plug-in Hybrid Electric Vehicle)",
    desc: "Kombinasi bensin dan listrik. Bisa diisi daya dan dapat menempuh jarak tertentu hanya dengan listrik sebelum beralih ke bensin.",
    iconKey: "phev",
  },
  {
    title: "Hybrid (HEV)",
    desc: "Menggabungkan mesin bensin dan motor listrik. Tidak perlu isi daya dari luar (charging mandiri).",
    iconKey: "hybrid",
  },
  {
    title: "Bensin",
    desc: "Menggunakan mesin pembakaran internal konvensional dengan bahan bakar bensin. Paling umum dan mudah dirawat.",
    iconKey: "bensin",
  },
  {
    title: "Diesel",
    desc: "Menggunakan bahan bakar diesel. Dikenal efisien untuk jarak jauh dan torsi besar.",
    iconKey: "diesel",
  },
];

// Top Resale Value Cars
export const TOP_RESALE_DATA: TopResaleCar[] = [
  {
    brand: "Toyota",
    model: "Innova Zenix",
    resale: "92%",
    image: "/cars/toyotazenixx.jpg",
  },
  {
    brand: "Mitsubishi",
    model: "Pajero Sport",
    resale: "90%",
    image: "/cars/mitsupajero.png",
  },
  {
    brand: "Toyota",
    model: "Fortuner",
    resale: "89%",
    image: "/cars/toyotafortuner.jpg",
  },
  {
    brand: "Honda",
    model: "CR-V",
    resale: "88%",
    image: "/cars/hondacrv.jpg",
  },
  {
    brand: "Toyota",
    model: "Rush",
    resale: "87%",
    image: "/cars/toyotarush.jpg",
  },
];

// Default values
export const DEFAULT_FORM_VALUES = {
  pred_years: 3,
  trusted_only: true,
  topn: 6,
  budget: BUDGET_MIN,
};

// Animation constants
export const ANIMATION_VARIANTS = {
  fadeIn: {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 }
  },
  stagger: {
    visible: {
      transition: {
        staggerChildren: 0.1
      }
    }
  },
  card: (i: number) => ({
    hidden: { opacity: 0, y: 20 },
    visible: { 
      opacity: 1, 
      y: 0, 
      transition: { delay: i * 0.06 } 
    }
  })
};