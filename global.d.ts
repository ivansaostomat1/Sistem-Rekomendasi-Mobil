import { Object3DNode, MaterialNode, GeometryNode } from '@react-three/fiber'
import { MeshLineGeometry, MeshLineMaterial } from 'meshline'

declare module '@react-three/fiber' {
  interface ThreeElements {
    meshLineGeometry: Object3DNode<MeshLineGeometry, typeof MeshLineGeometry>
    meshLineMaterial: Object3DNode<MeshLineMaterial, typeof MeshLineMaterial>
  }
}

declare global {
  namespace JSX {
    interface IntrinsicElements {
      meshLineGeometry: any
      meshLineMaterial: any
    }
  }
}