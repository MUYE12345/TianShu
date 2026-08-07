<template>
  <el-row :gutter="20">
    <!-- 预览区 -->
    <el-col :span="10">
      <el-card>
        <template #header><span><el-icon><Monitor /></el-icon> 桌宠预览</span></template>
        <div class="pet-preview">
          <div class="pet-canvas" :style="{ width: petSize + 'px', opacity: petOpacity }">
            <div class="pet-character" :style="{ fontSize: (petSize * 0.4) + 'px' }">
              <div class="pet-body" ref="petBody">
                <span v-if="currentFrame === 0">{{ petEmoji }}</span>
                <span v-else-if="currentFrame === 1">{{ petEmojiAlt }}</span>
                <span v-else>{{ petEmoji }}</span>
              </div>
            </div>
            <div class="pet-bubble" v-if="demoText">{{ demoText }}</div>
          </div>
        </div>
        <el-button @click="demoAnimation" style="width:100%;margin-top:8px">
          <el-icon><VideoPlay /></el-icon> 预览动画
        </el-button>
      </el-card>
    </el-col>

    <!-- 配置区 -->
    <el-col :span="14">
      <el-card>
        <template #header><span><el-icon><Setting /></el-icon> 桌宠配置</span></template>

        <el-form label-width="120px">
          <el-divider content-position="left">形象选择</el-divider>
          <el-form-item label="宠物形象">
            <el-radio-group v-model="petSkin" @change="onSkinChange">
              <el-radio-button value="cat">🐱 猫咪</el-radio-button>
              <el-radio-button value="dog">🐶 小狗</el-radio-button>
              <el-radio-button value="rabbit">🐰 兔子</el-radio-button>
              <el-radio-button value="bear">🐻 小熊</el-radio-button>
              <el-radio-button value="robot">🤖 机器人</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-divider content-position="left">尺寸与外观</el-divider>
          <el-form-item label="大小">
            <el-slider v-model="petSize" :min="60" :max="200" :step="10" show-input style="width:300px" />
          </el-form-item>
          <el-form-item label="透明度">
            <el-slider v-model="petOpacity" :min="0.3" :max="1" :step="0.1" show-input style="width:300px" />
          </el-form-item>

          <el-divider content-position="left">动画与交互</el-divider>
          <el-form-item label="动画速度">
            <el-radio-group v-model="animSpeed">
              <el-radio-button value="slow">慢速</el-radio-button>
              <el-radio-button value="normal">正常</el-radio-button>
              <el-radio-button value="fast">快速</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="空闲动画">
            <el-switch v-model="idleAnim" active-text="启用" inactive-text="禁用" />
          </el-form-item>

          <el-divider content-position="left">提醒设置</el-divider>
          <el-form-item label="天气提醒">
            <el-switch v-model="notifyWeather" />
          </el-form-item>
          <el-form-item label="休息提醒">
            <el-switch v-model="notifyRest" />
          </el-form-item>
          <el-form-item label="知识提醒">
            <el-switch v-model="notifyKnowledge" />
          </el-form-item>
          <el-form-item label="任务提醒">
            <el-switch v-model="notifyTask" />
          </el-form-item>

          <el-form-item>
            <el-button type="primary" @click="saveConfig"><el-icon><Check /></el-icon> 保存配置</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

// ── 宠物形象表 ──
const SKINS = {
  cat: { emoji: "🐱", alt: "😺", name: "猫咪" },
  dog: { emoji: "🐶", alt: "🦮", name: "小狗" },
  rabbit: { emoji: "🐰", alt: "🐇", name: "兔子" },
  bear: { emoji: "🐻", alt: "🧸", name: "小熊" },
  robot: { emoji: "🤖", alt: "⚙️", name: "机器人" },
}

// ── 状态 ──
const petSkin = ref(localStorage.getItem('pet_skin') || 'cat')
const petSize = ref(parseInt(localStorage.getItem('pet_size') || '120'))
const petOpacity = ref(parseFloat(localStorage.getItem('pet_opacity') || '0.9'))
const animSpeed = ref(localStorage.getItem('pet_anim_speed') || 'normal')
const idleAnim = ref(localStorage.getItem('pet_idle_anim') !== 'false')
const notifyWeather = ref(localStorage.getItem('pet_notify_weather') !== 'false')
const notifyRest = ref(localStorage.getItem('pet_notify_rest') !== 'false')
const notifyKnowledge = ref(localStorage.getItem('pet_notify_knowledge') !== 'false')
const notifyTask = ref(localStorage.getItem('pet_notify_task') !== 'false')

const currentFrame = ref(0)
const demoText = ref('')

const petEmoji = computed(() => SKINS[petSkin.value]?.emoji || "🐱")
const petEmojiAlt = computed(() => SKINS[petSkin.value]?.alt || "😺")

let animTimer = null

const onSkinChange = () => { currentFrame.value = 0 }

const demoAnimation = () => {
  let frame = 0
  const speedMap = { slow: 800, normal: 400, fast: 200 }
  const interval = speedMap[animSpeed.value] || 400
  const demos = ["你好~", "今天天气不错!", "该休息一下了", "有新知识哦!"]

  demoText.value = demos[Math.floor(Math.random() * demos.length)]

  if (animTimer) clearInterval(animTimer)
  animTimer = setInterval(() => {
    frame = (frame + 1) % 4
    currentFrame.value = frame
    if (frame === 3) {
      clearInterval(animTimer)
      animTimer = null
      demoText.value = ''
    }
  }, interval)
}

const saveConfig = () => {
  localStorage.setItem('pet_skin', petSkin.value)
  localStorage.setItem('pet_size', petSize.value.toString())
  localStorage.setItem('pet_opacity', petOpacity.value.toString())
  localStorage.setItem('pet_anim_speed', animSpeed.value)
  localStorage.setItem('pet_idle_anim', idleAnim.value.toString())
  localStorage.setItem('pet_notify_weather', notifyWeather.value.toString())
  localStorage.setItem('pet_notify_rest', notifyRest.value.toString())
  localStorage.setItem('pet_notify_knowledge', notifyKnowledge.value.toString())
  localStorage.setItem('pet_notify_task', notifyTask.value.toString())
  ElMessage.success('桌宠配置已保存')
}
</script>

<style scoped>
.pet-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 250px;
  background: linear-gradient(180deg, #e8f4fd 0%, #f0f2f5 100%);
  border-radius: 12px;
  position: relative;
}
.pet-canvas {
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.3s;
}
.pet-character {
  animation: float 3s ease-in-out infinite;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}
.pet-body {
  text-align: center;
  transition: transform 0.2s;
}
.pet-body span {
  display: inline-block;
  animation: blink 0.1s;
}
.pet-bubble {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  padding: 8px 16px;
  margin-top: 12px;
  font-size: 14px;
  color: #333;
  position: relative;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  animation: fadeIn 0.3s ease;
}
.pet-bubble::before {
  content: '';
  position: absolute;
  top: -8px;
  left: 50%;
  margin-left: -8px;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-bottom: 8px solid #fff;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
