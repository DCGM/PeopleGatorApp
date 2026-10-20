import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PeopleCard from '@/components/custom/PeopleCard.vue'
import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'
import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'
import SimilarPersonItem from '@/components/custom/SimilarPersonItem.vue'

const canonicalFace = 'saved-face-outside-current-evidence'
const global = {
  stubs: { PersonPortrait: true, PersonThumbnailPicker: true, RouterLink: RouterLinkStub },
}

describe('person identity portraits', () => {
  it('passes the same saved reference through search, profile, discovery and scan assignment choices', () => {
    const wrappers = [
      mount(PeopleCard, {
        global,
        props: { name: 'Ada', thumbnailFaceId: canonicalFace, faces: 3, names: 1 },
      }),
      mount(PersonEditableDetails, {
        global,
        props: {
          modelValue: { name: 'Ada', shortDescription: '', article: '', aliases: [] },
          personId: 'ada',
          thumbnailFaceId: canonicalFace,
          thumbnailMode: 'manual',
          faceCount: 3,
          mentionCount: 1,
          libraryCount: 1,
          wikidataId: '',
          nationalLibraryAuthorityId: '',
        },
      }),
      mount(PersonDiscoveryPanel, {
        global,
        props: {
          currentName: 'Other Person',
          referenceFaceCount: 1,
          faces: [],
          people: [
            {
              id: 'ada',
              name: 'Ada',
              shortDescription: '',
              aliases: [],
              thumbnailFaceId: canonicalFace,
              matchedFaceIds: ['different-match'],
            },
          ],
        },
      }),
      mount(SimilarPersonItem, {
        global,
        props: {
          person: {
            id: 'ada',
            name: 'Ada',
            thumbnailFaceId: canonicalFace,
            faceId: 'different-evidence',
            nerMentions: 1,
            detections: 3,
            source: 'page',
          },
        },
      }),
    ]
    for (const wrapper of wrappers) {
      expect(wrapper.getComponent({ name: 'PersonPortrait' }).props('faceId')).toBe(canonicalFace)
      wrapper.unmount()
    }
  })
})
