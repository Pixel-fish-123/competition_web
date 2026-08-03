import TriangleBoard from './TriangleBoard.vue'
import TriangleControls from './TriangleControls.vue'

export const pluginName = 'triangle_occupy'

export { TriangleBoard, TriangleControls }

export default {
  name: pluginName,
  board: TriangleBoard,
  controls: TriangleControls,
}
