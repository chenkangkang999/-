<script setup lang="ts">
import type { WorkspacePage } from "@/config/workspace";
defineProps<{ scene: WorkspacePage }>();
</script>
<template>
  <svg class="medical-scene-art" :data-scene="scene" viewBox="0 0 440 225" fill="none" aria-hidden="true">
    <ellipse cx="247" cy="211" rx="176" ry="10" fill="var(--scene-shadow)" />
    <g stroke="var(--scene-line)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <template v-if="scene === 'home' || scene === 'consultation'">
        <path d="M29 199h383M48 183V34h123v149M62 47h95v91H62z" opacity=".6" />
        <path d="M109 47v91M62 92h95" opacity=".45" />
        <rect x="281" y="39" width="108" height="102" rx="10" fill="var(--scene-paper)" />
        <path d="M296 72h29l8-15 13 37 11-20h18M299 111h42M299 122h63" stroke="var(--scene-accent)" opacity=".65" />
        <rect x="173" y="124" width="135" height="12" rx="4" fill="var(--scene-gold)" stroke="none" />
        <path d="M184 136v66M297 136v66M219 202h51" />
        <path d="M94 129c-9 2-18 11-20 27l-5 45h64l-3-48c-1-14-9-22-18-24" fill="var(--scene-paper)" />
        <path d="M91 131l12 20 13-20M101 151v39M82 149l-5 40M123 147l19 20 33-28" />
        <path d="M139 168c13 4 27-11 36-25M174 141l15-3" stroke="var(--scene-accent)" stroke-width="5" />
        <path d="M90 126v-13h24v16" fill="var(--scene-skin)" stroke="none" />
        <ellipse cx="101" cy="98" rx="23" ry="27" fill="var(--scene-skin)" stroke="none" />
        <path d="M77 98c-10-33 8-47 27-43 25-2 33 15 21 45l-7-20c-9 8-22 10-36 7z" fill="var(--scene-accent)" stroke="none" />
        <path d="M92 125c0 10-3 15-4 24M114 127c1 10 2 15 2 24M89 150c1 14 26 14 27 0" stroke="var(--scene-accent)" />
        <circle cx="102" cy="165" r="5" fill="var(--scene-paper)" />
        <path d="M244 158c5-19 20-28 34-28 23 0 39 17 42 39l3 33h-84z" fill="var(--scene-soft)" />
        <path d="M264 133v-15h24v17" fill="var(--scene-skin)" stroke="none" />
        <ellipse cx="278" cy="100" rx="23" ry="27" fill="var(--scene-skin)" stroke="none" />
        <path d="M254 99c-10-26 3-43 23-43 21 0 34 18 24 42l-6-18c-11 5-23 3-35 7z" fill="var(--scene-dark)" stroke="none" />
        <path d="M254 160l-27-14-24-3M298 161l-14 31h-36M247 201v-20M316 182h25v19" />
        <rect x="186" y="97" width="53" height="36" rx="7" fill="var(--scene-paper)" />
        <path d="m200 133 1 8 10-8M196 109h32M196 118h22" opacity=".6" />
        <path d="M370 202v-40M369 176c-19-2-24-15-23-23 16 0 23 8 23 23ZM371 186c16-2 24-16 22-24-15 1-22 10-22 24Z" fill="var(--scene-soft)" />
        <path d="m353 200 4 11h29l4-11" fill="var(--scene-gold)" stroke="none" />
      </template>
      <template v-else-if="scene === 'agents'">
        <path d="M102 69h54M105 161h52M278 69h58M278 161h58M216 49v129" stroke-dasharray="5 6" opacity=".6" />
        <path d="m139 65 37 32M139 165l37-35M266 97l38-31M266 130l38 32" stroke-dasharray="5 6" />
        <rect x="161" y="66" width="112" height="110" rx="20" fill="var(--scene-paper)" />
        <path d="M194 103h46v40h-46zM206 103V91h23v12M210 119v14M202 126h17" stroke="var(--scene-accent)" stroke-width="2" />
        <circle cx="97" cy="55" r="30" fill="var(--scene-soft)" /><path d="M81 54h31M96 39v31" stroke="var(--scene-accent)" />
        <circle cx="92" cy="164" r="30" fill="var(--scene-gold)" /><path d="M77 170h29M79 156h26v21H79zM86 150h12" />
        <circle cx="343" cy="55" r="30" fill="var(--scene-gold)" /><path d="M328 44h30v23h-30zM334 52h18M334 58h13" />
        <circle cx="348" cy="164" r="30" fill="var(--scene-soft)" /><path d="m348 147-15 6v10c0 10 15 17 15 17s15-7 15-17v-10zM341 162l5 5 9-11" stroke="var(--scene-accent)" />
        <path d="M170 192h97M182 202h72" opacity=".5" />
      </template>
      <template v-else-if="scene === 'monitoring'">
        <rect x="69" y="35" width="283" height="151" rx="13" fill="var(--scene-paper)" />
        <path d="M84 57h253M84 164h253M111 67v84M132 67v84M153 67v84M174 67v84M195 67v84M216 67v84M237 67v84M258 67v84M279 67v84M300 67v84" opacity=".2" />
        <path d="M84 111h43l12-17 13 36 19-57 19 67 14-29h25l10-12 12 22 13-30 13 20h60" stroke="var(--scene-accent)" stroke-width="2.5" />
        <path d="M202 186v20M172 207h64" />
        <rect x="287" y="130" width="101" height="79" rx="10" fill="var(--scene-gold)" stroke="none" />
        <path d="M304 190h65M311 190v-24M327 190v-36M343 190v-19M359 190v-42" stroke="var(--scene-accent)" stroke-width="6" />
        <circle cx="74" cy="173" r="27" fill="var(--scene-soft)" /><path d="m61 174 9 9 18-20" stroke="var(--scene-accent)" stroke-width="2.5" />
      </template>
      <template v-else-if="scene === 'billing'">
        <path d="M66 193h323M86 83v-23h166v133H86z" fill="var(--scene-soft)" />
        <path d="m91 59 21-20h54l15 20" fill="var(--scene-soft)" />
        <rect x="128" y="23" width="137" height="166" rx="9" fill="var(--scene-paper)" />
        <path d="M148 59h98M148 78h73M148 97h98M148 116h98M148 135h62M148 158h24M224 158h21" opacity=".6" />
        <path d="M189 39h16M197 31v16" stroke="var(--scene-accent)" stroke-width="2" />
        <rect x="254" y="98" width="88" height="108" rx="10" fill="var(--scene-gold)" />
        <rect x="268" y="112" width="60" height="22" rx="3" fill="var(--scene-paper)" />
        <path d="M270 149h9M294 149h9M318 149h8M270 166h9M294 166h9M318 166h8M270 183h9M294 183h9M318 183h8" stroke="var(--scene-accent)" stroke-width="4" />
        <circle cx="92" cy="158" r="25" fill="var(--scene-gold)" /><path d="m80 158 8 8 16-19" stroke="var(--scene-accent)" stroke-width="2.5" />
      </template>
    </g>
  </svg>
</template>
