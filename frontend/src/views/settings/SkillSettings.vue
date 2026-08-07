<template>
  <el-card>
    <template #header>
      <div style="display:flex;justify-content:space-between">
        <span><el-icon><MagicStick /></el-icon> SKILL管理</span>
        <el-button size="small" type="primary" @click="refreshSkills">刷新</el-button>
      </div>
    </template>

    <el-table :data="skills" stripe>
      <el-table-column prop="name" label="SKILL名" width="120" />
      <el-table-column prop="description" label="描述" min-width="250" />
      <el-table-column prop="version" label="版本" width="80" />
      <el-table-column label="状态" width="80">
        <template #default="{row}">
          <el-tag :type="row.enabled?'success':'info'" size="small">{{ row.enabled?'已启用':'已禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{row}">
          <el-button size="small" @click="toggleSkill(row)">{{ row.enabled?'禁用':'启用' }}</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="skills.length===0" description="暂无SKILL" />
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '../../utils/request'

const skills = ref([])

onMounted(refreshSkills)

async function refreshSkills() {
  try {
    const res = await request.get('/api/skills')
    skills.value = res?.items || res || []
  } catch {}
}

async function toggleSkill(skill) {
  try {
    await request.post(`/api/skills/${skill.name}/enable`)
    skill.enabled = !skill.enabled
  } catch {}
}
</script>
