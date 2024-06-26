from typing import Any, Dict, List, Literal, Tuple, Type, Union

import numpy as np
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from inference.core.utils.image_utils import ImageType, load_image
from inference.core.workflows.constants import (
    IMAGE_TYPE_KEY,
    IMAGE_VALUE_KEY,
    LEFT_TOP_X_KEY,
    LEFT_TOP_Y_KEY,
    ORIGIN_COORDINATES_KEY,
    ORIGIN_SIZE_KEY,
    PARENT_ID_KEY,
)
from inference.core.workflows.core_steps.common.utils import (
    extract_origin_size_from_images_batch,
)
from inference.core.workflows.entities.base import OutputDefinition
from inference.core.workflows.entities.types import (
    BATCH_OF_IMAGES_KIND,
    BATCH_OF_PARENT_ID_KIND,
    FLOAT_ZERO_TO_ONE_KIND,
    FloatZeroToOne,
    FlowControl,
    StepOutputImageSelector,
    WorkflowImageSelector,
    WorkflowParameterSelector,
)
from inference.core.workflows.prototypes.block import (
    WorkflowBlock,
    WorkflowBlockManifest,
)

LONG_DESCRIPTION = """
Crop a Region of Interest (RoI) from an image, using relative coordinates.

This is useful when placed after an ObjectDetection block as part of a multi-stage 
workflow. For example, you could use an ObjectDetection block to detect objects, then 
the RelativeStaticCrop block to crop objects, then an OCR block to run character 
recognition on each of the individual cropped regions.
"""


class BlockManifest(WorkflowBlockManifest):
    model_config = ConfigDict(
        json_schema_extra={
            "short_description": "Use relative coordinates for cropping.",
            "long_description": LONG_DESCRIPTION,
            "license": "Apache-2.0",
            "block_type": "transformation",
        }
    )
    type: Literal["RelativeStaticCrop"]
    name: str = Field(description="Unique name of step in workflows")
    images: Union[WorkflowImageSelector, StepOutputImageSelector] = Field(
        description="Reference an image to be used as input for step processing",
        examples=["$inputs.image", "$steps.cropping.crops"],
        validation_alias=AliasChoices("images", "image"),
    )
    x_center: Union[
        FloatZeroToOne, WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND])
    ] = Field(
        description="Center X of static crop (relative coordinate 0.0-1.0)",
        examples=[0.3, "$inputs.center_x"],
    )
    y_center: Union[
        FloatZeroToOne, WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND])
    ] = Field(
        description="Center Y of static crop (relative coordinate 0.0-1.0)",
        examples=[0.3, "$inputs.center_y"],
    )
    width: Union[
        FloatZeroToOne, WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND])
    ] = Field(
        description="Width of static crop (relative value 0.0-1.0)",
        examples=[0.3, "$inputs.width"],
    )
    height: Union[
        FloatZeroToOne, WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND])
    ] = Field(
        description="Height of static crop (relative value 0.0-1.0)",
        examples=[0.3, "$inputs.height"],
    )

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(name="crops", kind=[BATCH_OF_IMAGES_KIND]),
            OutputDefinition(name="parent_id", kind=[BATCH_OF_PARENT_ID_KIND]),
        ]


class RelativeStaticCropBlock(WorkflowBlock):

    @classmethod
    def get_manifest(cls) -> Type[BaseModel]:
        return BlockManifest

    async def run_locally(
        self,
        images: List[dict],
        x_center: float,
        y_center: float,
        width: float,
        height: float,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], FlowControl]]:
        decoded_images = [load_image(e) for e in images]
        decoded_images = [
            i[0] if i[1] is True else i[0][:, :, ::-1] for i in decoded_images
        ]
        images_parents = [i[PARENT_ID_KEY] for i in images]
        origin_image_shape = extract_origin_size_from_images_batch(
            input_images=images,
            decoded_images=decoded_images,
        )
        crops = [
            take_static_crop(
                image=i,
                x_center=x_center,
                y_center=y_center,
                width=width,
                height=height,
                origin_size=size,
                image_parent=image_parent,
            )
            for i, image_parent, size in zip(
                decoded_images, images_parents, origin_image_shape
            )
        ]
        return [{"crops": c, PARENT_ID_KEY: c[PARENT_ID_KEY]} for c in crops]


def take_static_crop(
    image: np.ndarray,
    x_center: float,
    y_center: float,
    width: float,
    height: float,
    origin_size: dict,
    image_parent: str,
) -> Dict[str, Union[str, np.ndarray]]:
    x_center = round(image.shape[1] * x_center)
    y_center = round(image.shape[0] * y_center)
    width = round(image.shape[1] * width)
    height = round(image.shape[0] * height)
    x_min = round(x_center - width / 2)
    y_min = round(y_center - height / 2)
    x_max = round(x_min + width)
    y_max = round(y_min + height)
    cropped_image = image[y_min:y_max, x_min:x_max]
    return {
        IMAGE_TYPE_KEY: ImageType.NUMPY_OBJECT.value,
        IMAGE_VALUE_KEY: cropped_image,
        PARENT_ID_KEY: image_parent,
        ORIGIN_COORDINATES_KEY: {
            LEFT_TOP_X_KEY: x_min,
            LEFT_TOP_Y_KEY: y_min,
            ORIGIN_SIZE_KEY: origin_size,
        },
    }
