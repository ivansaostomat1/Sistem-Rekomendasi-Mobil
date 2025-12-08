/* eslint-disable react/no-unknown-property */
'use client';

import React, { Suspense, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, useGLTF, Stage, Html } from '@react-three/drei';

interface ModelViewerProps {
  url: string;
  width?: number | string;
  height?: number | string;
  onClick?: () => void;
}

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const ref = useRef<any>(null);

  // --- PERUBAHAN: HAPUS useFrame untuk mematikan rotasi manual ---
  // Kode useFrame() yang menyebabkan rotasi 0.01 per frame
  // telah dihapus agar model tidak berputar.
  
  return (
    <primitive 
      ref={ref}
      object={scene} 
      scale={3} // ADJUST SCALE: DeLorean biasanya raksasa, kita kecilkan dulu
      position={[0, 0, 0]}
    />
  );
}

function Loader() {
  return (
    <Html center>
      <div className="text-xs font-bold text-teal-500 bg-white/80 px-2 py-1 rounded">
        Loading...
      </div>
    </Html>
  );
}

export default function ModelViewer({ 
  url, 
  width = 200, // Mengubah default width/height kembali ke nilai yang realistis untuk tombol (200px)
  height = 200, 
  onClick 
}: ModelViewerProps) {
  
  return (
    <div 
      style={{ width, height, cursor: 'pointer' }} 
      className="relative z-50 group"
      onClick={onClick}
      title="Klik untuk Chat AI"
    >
      {/* Efek Hover Bulat di belakang mobil */}
      <div className="absolute inset-0 bg-gradient-to-tr from-emerald-500/20 to-cyan-500/20 rounded-full blur-xl group-hover:blur-2xl transition-all" />

      <Canvas 
        shadows 
        dpr={[1, 2]} 
        camera={{ position: [0, 2, 8], fov: 50 }}
        gl={{ preserveDrawingBuffer: true, alpha: true }}
      >
        <ambientLight intensity={1} />
        <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} intensity={1} />
        
        <Suspense fallback={<Loader />}>
          <Stage environment="city" intensity={0.6} adjustCamera={1.2}>
            <Model url={url} />
          </Stage>
        </Suspense>

        <OrbitControls 
            enableZoom={false} 
            enablePan={false} 
            autoRotate={false} // Sudak benar, mematikan rotasi bawaan OrbitControls
            autoRotateSpeed={0} // Prop ini tidak diperlukan lagi jika autoRotate=false
        />
      </Canvas>
    </div>
  );
}